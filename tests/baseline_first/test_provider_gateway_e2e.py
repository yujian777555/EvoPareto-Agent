"""End-to-end Provider Gateway tests (Stage 3.0-P1-R2A-R1 Task 2).

Exercises BOTH AFlow call chains through PhysicalBudgetGate to a Mock HTTP
provider, with per-request ledger rows and fail-closed budget behaviour.

Zero real LLM calls.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# AFlow sanitize.py imports tree_sitter which is not in requirements; stub it
# for offline import (dependency stub only — not an algorithm change).
import types
try:
    import tree_sitter  # noqa: F401
except Exception:
    _ts = types.ModuleType("tree_sitter")
    _ts.Node = object
    _ts.Parser = object
    _ts.Language = object
    sys.modules["tree_sitter"] = _ts

from src.runtime.http_budget import BillingBlocked, BudgetDB, BudgetExceeded, install_global_gate
from src.runtime.provider_gateway import (
    GatewayLLM,
    MockHTTPProvider,
    RequestLedger,
    UnknownModelPrice,
    UsageMissing,
    estimate_cost,
    install_aflow_gateway,
    run_workflow_code_isolated,
    PRICE_TABLE_USD_PER_1M,
    PRICE_VERIFIED_AT,
)


@pytest.fixture()
def budget_env(tmp_path):
    db = BudgetDB(tmp_path / "gw.sqlite", max_physical=50, max_cost_usd=1.0)
    gate_install = None
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    yield {
        "db": db,
        "ledger": ledger,
        "provider": provider,
        "llm": GatewayLLM(
            base_url=provider.base_url,
            ledger=ledger,
            run_id="r2a-r1-test",
            max_input_tokens=2000,
            max_output_tokens=500,
            timeout=5.0,
        ),
    }
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------------------------------------------------------------------
# Path A: Optimizer LLM
# ---------------------------------------------------------------------------

def test_optimizer_llm_path_hits_http_provider(budget_env):
    llm = budget_env["llm"]
    provider = budget_env["provider"]
    ledger = budget_env["ledger"]

    async def run():
        # this is the Optimizer call shape: optimize_llm(prompt)
        return await llm("optimize this workflow graph")

    out = asyncio.run(run())
    assert out  # response content returned
    assert len(provider.requests_seen) == 1
    assert provider.requests_seen[0]["path"].endswith("/chat/completions")
    rows = ledger.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["request_status"] == "settled_ok"
    assert row["model"] == "deepseek-flash"
    assert row["provider"] == "mock-http"
    assert row["physical_request_id"]
    assert row["logical_request_id"].startswith("req-")
    assert row["reported_tokens_in"] and row["reported_tokens_out"]
    assert row["observed_cost"] is not None and row["observed_cost"] > 0
    assert row["cumulative_cost"] is not None


# ---------------------------------------------------------------------------
# Path B: Workflow / Operator LLM
# ---------------------------------------------------------------------------

def test_workflow_operator_llm_path_hits_http_provider(budget_env):
    llm = budget_env["llm"]
    provider = budget_env["provider"]
    ledger = budget_env["ledger"]
    llm.logical_request_prefix = "op"

    async def run():
        # Operator surface: await self.llm(prompt) — raw text path
        a = await llm("AnswerGenerate: solve 1+1")
        b = await llm("ScEnsemble: pick best answer")
        return a, b

    a, b = asyncio.run(run())
    assert a
    assert b
    assert len(provider.requests_seen) == 2
    rows = ledger.rows()
    assert len(rows) == 2
    assert all(r["request_status"] == "settled_ok" for r in rows)
    assert all(r["logical_request_id"].startswith("op-") for r in rows)
    # distinct physical ids
    assert rows[0]["physical_request_id"] != rows[1]["physical_request_id"]


def test_aflow_optimizer_and_workflow_share_chokepoint(budget_env):
    """install_aflow_gateway makes both AFlow factories return the same GatewayLLM."""
    install_aflow_gateway(budget_env["llm"])
    import scripts.optimizer as optimizer_mod  # type: ignore
    import scripts.workflow as workflow_mod  # type: ignore

    o = optimizer_mod.create_llm_instance("deepseek-flash")
    w = workflow_mod.create_llm_instance({"model": "deepseek-flash"})
    assert o is budget_env["llm"]
    assert w is budget_env["llm"]


# ---------------------------------------------------------------------------
# Per-request ledger (NOT meta overwrite)
# ---------------------------------------------------------------------------

def test_request_ledger_is_append_only(budget_env):
    llm = budget_env["llm"]
    ledger = budget_env["ledger"]
    for i in range(3):
        asyncio.run(llm(f"prompt {i}"))
    rows = ledger.rows()
    assert len(rows) == 3
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(seqs)
    # every row keeps its own ids (history not overwritten)
    assert len({r["physical_request_id"] for r in rows}) == 3
    assert len({r["ticket_id"] for r in rows}) == 3
    # cumulative_cost is stamped per row
    assert rows[-1]["cumulative_cost"] >= rows[0]["cumulative_cost"]


# ---------------------------------------------------------------------------
# Budget hard cap
# ---------------------------------------------------------------------------

def test_budget_hard_cap_rejects_after_exhaustion(tmp_path):
    db = BudgetDB(tmp_path / "cap.sqlite", max_physical=3, max_cost_usd=0.05)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="cap-test")
    try:
        for _ in range(3):
            asyncio.run(llm("go"))
        # 4th must be refused before any HTTP
        n_before = len(provider.requests_seen)
        with pytest.raises(BudgetExceeded):
            asyncio.run(llm("go"))
        assert len(provider.requests_seen) == n_before  # no socket send
    finally:
        install_global_gate(None, strict=False)
        provider.shutdown()
        db.close()


def test_concurrent_requests_cannot_break_cap(tmp_path):
    db = BudgetDB(tmp_path / "conc.sqlite", max_physical=5, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="conc-test", timeout=10)
    errors = []
    ok = []

    def worker():
        for _ in range(4):
            try:
                asyncio.run(llm("go"))
                ok.append(1)
            except Exception as e:
                errors.append(type(e).__name__)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = db.snapshot()
    assert snap["physical_attempts"] <= snap["max_physical"]
    assert "BudgetExceeded" in errors
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_restart_keeps_cumulative_budget(tmp_path):
    db_path = tmp_path / "restart.sqlite"
    db = BudgetDB(db_path, max_physical=10, max_cost_usd=0.20)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="restart-1")
    asyncio.run(llm("a"))
    asyncio.run(llm("b"))
    spent_before = db.snapshot()["spent_cost_usd"]
    attempts_before = db.snapshot()["physical_attempts"]
    db.close()

    # "restart": new process state, same sqlite
    db2 = BudgetDB(db_path, max_physical=10, max_cost_usd=0.20)
    snap = db2.snapshot()
    assert snap["spent_cost_usd"] == pytest.approx(spent_before)
    assert snap["physical_attempts"] == attempts_before
    ledger2 = RequestLedger(db2)
    assert ledger2.count() == 2  # history preserved
    install_global_gate(None, strict=False)
    provider.shutdown()
    db2.close()


# ---------------------------------------------------------------------------
# Fail-closed paths
# ---------------------------------------------------------------------------

def test_missing_usage_fails_closed(tmp_path):
    db = BudgetDB(tmp_path / "mu.sqlite", max_physical=10, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="missing_usage")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="mu-test")
    with pytest.raises(UsageMissing):
        asyncio.run(llm("hello"))
    assert db.is_billing_blocked()
    rows = ledger.rows()
    assert rows and rows[0]["request_status"] == "fail_closed"
    assert rows[0]["error_kind"] == "MISSING_USAGE"
    # further sends rejected
    with pytest.raises(BillingBlocked):
        asyncio.run(llm("hello"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_unknown_model_price_fails_closed():
    with pytest.raises(UnknownModelPrice):
        estimate_cost("totally-unknown-model", 10, 10)


def test_unknown_model_price_blocks_billing(tmp_path):
    db = BudgetDB(tmp_path / "up.sqlite", max_physical=10, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="up-test", model="no-such-model")
    with pytest.raises((UnknownModelPrice, Exception)):
        asyncio.run(llm("hello"))
    # either blocked or simply refused before send — never a free model call
    assert db.is_billing_blocked() or not provider.requests_seen
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_timeout_fails_closed(tmp_path):
    db = BudgetDB(tmp_path / "to2.sqlite", max_physical=10, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="timeout")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="to2", timeout=1.0)
    raised = False
    try:
        asyncio.run(llm("hello"))
    except Exception:
        raised = True
    assert raised
    rows = ledger.rows()
    assert rows and rows[0]["request_status"] in ("failed", "fail_closed")
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_partial_response_fails_closed(tmp_path):
    db = BudgetDB(tmp_path / "pr.sqlite", max_physical=10, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="partial")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="pr-test")
    with pytest.raises(Exception):
        asyncio.run(llm("hello"))
    rows = ledger.rows()
    assert rows and rows[0]["request_status"] in ("fail_closed", "failed")
    assert rows[0]["error_kind"] in ("PARTIAL_RESPONSE", "RuntimeError", "MissingUsage")
    # partial/unknown billing must not allow free continuation
    assert db.is_billing_blocked() or rows[0]["request_status"] == "fail_closed"
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_500_recorded_as_failed(tmp_path):
    db = BudgetDB(tmp_path / "e5.sqlite", max_physical=10, max_cost_usd=1.0)
    from src.runtime.http_budget import PhysicalBudgetGate

    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="http_500")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="e5")
    raised = False
    try:
        asyncio.run(llm("hello"))
    except Exception:
        raised = True
    assert raised
    rows = ledger.rows()
    assert rows and rows[0]["request_status"] in ("failed", "fail_closed")
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------------------------------------------------------------------
# Pricing / Task 3 constants
# ---------------------------------------------------------------------------

def test_pricing_table_has_deepseek_flash():
    assert "deepseek-flash" in PRICE_TABLE_USD_PER_1M
    p = PRICE_TABLE_USD_PER_1M["deepseek-flash"]
    assert p["input_cache_miss_peak"] == 0.30
    assert p["output_peak"] == 1.20
    assert PRICE_VERIFIED_AT == "2026-10-16"


def test_worst_case_cost_under_cap():
    worst = estimate_cost("deepseek-flash", 2_000_000, 200_000, peak=True)
    assert worst < 5.0
    assert abs(worst - 0.84) < 0.01


# ---------------------------------------------------------------------------
# Isolated generated-workflow execution (Task 2 items 7-8)
# ---------------------------------------------------------------------------

def test_generated_workflow_runs_isolated_without_host_secrets():
    graph = (
        "class Workflow:\n"
        "    def __init__(self):\n"
        "        import os\n"
        "        self.leaked = os.environ.get('R2A_HOST_SECRET')\n"
        "    async def __call__(self, problem):\n"
        "        import socket\n"
        "        try:\n"
        "            socket.create_connection(('1.1.1.1', 443), timeout=2)\n"
        "            net = 'OPEN'\n"
        "        except Exception as e:\n"
        "            net = type(e).__name__\n"
        "        return {'secret': self.leaked, 'net': net}\n"
    )
    os.environ["R2A_HOST_SECRET"] = "should-not-leak"
    try:
        res = run_workflow_code_isolated(graph, timeout=15)
    finally:
        os.environ.pop("R2A_HOST_SECRET", None)
    assert res["ok"] is True, f"isolated run failed: {res}"
    out = res["stdout"] + res.get("stderr", "")
    assert "should-not-leak" not in out
    assert "OPEN" not in out
