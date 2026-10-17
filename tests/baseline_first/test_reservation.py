"""Reservation correctness + prompt-length distribution tests (Task C)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.http_budget import BudgetDB, BudgetExceeded, PhysicalBudgetGate, install_global_gate
from src.runtime.provider_gateway import (
    GatewayLLM,
    MockHTTPProvider,
    RequestLedger,
    conservative_input_tokens,
    worst_case_cost,
)


@pytest.fixture()
def env(tmp_path):
    db = BudgetDB(tmp_path / "r.sqlite", max_physical=20, max_cost_usd=0.01)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.0005)  # deliberately LOW default
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(
        base_url=provider.base_url, ledger=ledger, run_id="res-test",
        max_input_tokens=2000, max_output_tokens=500, timeout=6.0,
    )
    yield {"db": db, "llm": llm, "ledger": ledger, "provider": provider}
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_reservation_is_worst_case_not_flat_default(env):
    """A request must reserve the peak cache-miss cost for its own token bound.

    The flat est_cost_per_request=0.0005 must NOT be used when the caller
    supplies a larger worst-case reserve_cost.
    """
    llm = env["llm"]
    asyncio.run(llm("hello world"))
    rows = env["ledger"].rows()
    assert rows
    est_in = conservative_input_tokens("hello world")
    expected = worst_case_cost("deepseek-flash", est_in, 500)
    assert rows[0]["reserved_cost"] == pytest.approx(expected)
    assert rows[0]["reserved_cost"] > 0.0005  # not the flat default


def test_low_budget_rejects_expensive_request(tmp_path):
    """A $0.001 cap cannot fund a 2000/500 peak request (~$0.0012)."""
    db = BudgetDB(tmp_path / "low.sqlite", max_physical=10, max_cost_usd=0.0001)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.0005)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(
        base_url=provider.base_url, ledger=ledger,
        max_input_tokens=2000, max_output_tokens=500,
    )
    with pytest.raises(BudgetExceeded):
        asyncio.run(llm("x" * 500))
    assert len(provider.requests_seen) == 0  # refused BEFORE send
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_reserve_cost_matches_peak_formula(env):
    llm = env["llm"]
    asyncio.run(llm("abc"))
    row = env["ledger"].rows()[0]
    # peak cache-miss: est_in*0.30/1M + 500*1.20/1M
    est_in = conservative_input_tokens("abc")
    assert row["reserved_cost"] == pytest.approx(est_in * 0.30 / 1e6 + 500 * 1.20 / 1e6)


def test_prompt_length_distribution_recorded():
    p = ROOT / "results" / "final_live_admission" / "optimizer_prompt_lengths.json"
    assert p.exists(), "run run_full_aflow_mock.py first"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["n"] >= 1
    assert d["max"] >= 1
    assert d["max"] > 2000, "optimizer prompt exceeds the frozen 2000/request cap"


def test_token_limit_proposal_documented():
    p = ROOT / "results" / "final_live_admission" / "token_limit_proposal.json"
    assert p.exists()
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["current_max_input_per_request"] == 2000
    assert d["observed_max_prompt_len"] > 2000
    assert d["proposed_max_input_per_request"] > 2000
    assert d["pilot_authorization_unchanged"] is True
    assert d["worst_case_cost_under_5usd"] is True
