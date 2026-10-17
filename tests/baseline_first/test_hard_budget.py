"""Token / cost hard-cap and structured-output fail-closed tests (R2A-R2 Task 2-3)."""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.http_budget import (
    BillingBlocked,
    BudgetDB,
    BudgetExceeded,
    PhysicalBudgetGate,
    install_global_gate,
)
from src.runtime.provider_gateway import (
    GatewayLLM,
    InputTokenCapExceeded,
    MockHTTPProvider,
    OutputTokenCapExceeded,
    RequestLedger,
    StructuredOutputError,
    UnknownModelPrice,
    conservative_input_tokens,
    estimate_cost,
    worst_case_cost,
)


@pytest.fixture()
def env(tmp_path):
    db = BudgetDB(tmp_path / "b.sqlite", max_physical=50, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(
        base_url=provider.base_url, ledger=ledger, run_id="hardcap",
        max_input_tokens=2000, max_output_tokens=500, timeout=6.0,
    )
    yield {"db": db, "llm": llm, "ledger": ledger, "provider": provider}
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------- pricing ----------------

def test_estimate_cost_defaults_to_peak():
    # 100 in * 0.30/1M + 20 out * 1.20/1M  (PEAK cache-miss)
    c = estimate_cost("deepseek-flash", 100, 20)
    assert c == pytest.approx(100 * 0.30 / 1e6 + 20 * 1.20 / 1e6)


def test_worst_case_matches_token_bounds():
    w = worst_case_cost("deepseek-flash", 2000, 500)
    assert w == pytest.approx(2000 * 0.30 / 1e6 + 500 * 1.20 / 1e6)
    assert w > 0


def test_unknown_model_price_fail_closed():
    with pytest.raises(UnknownModelPrice):
        estimate_cost("nope-model", 1, 1)
    with pytest.raises(UnknownModelPrice):
        worst_case_cost("nope-model", 1, 1)


def test_conservative_token_bound_not_naive_quarter():
    s = "你好世界" * 10  # CJK
    assert conservative_input_tokens(s) >= len(s)  # never under-estimate


# ---------------- input token cap ----------------

def test_input_token_cap_blocks_before_send(env):
    llm = env["llm"]
    n = len(env["provider"].requests_seen)
    with pytest.raises(InputTokenCapExceeded):
        asyncio.run(llm("x" * 3000))  # > 2000 + 8
    assert len(env["provider"].requests_seen) == n  # no HTTP


def test_output_token_cap_positive_required(tmp_path):
    db = BudgetDB(tmp_path / "c.sqlite", max_physical=5, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_output_tokens=0)
    with pytest.raises(OutputTokenCapExceeded):
        asyncio.run(llm("hi"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------- reservation = worst-case ----------------

def test_reservation_covers_worst_case(env):
    llm = env["llm"]
    asyncio.run(llm("hello"))
    rows = env["ledger"].rows()
    assert rows
    # reserved_cost must be the worst-case for (2000, 500) peak
    est_in = conservative_input_tokens("hello")
    expected = worst_case_cost("deepseek-flash", est_in, 500)
    assert rows[0]["reserved_cost"] == pytest.approx(expected)


def test_hard_request_cap(tmp_path):
    db = BudgetDB(tmp_path / "d.sqlite", max_physical=3, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_input_tokens=2000, max_output_tokens=500)
    for _ in range(3):
        asyncio.run(llm("hi"))
    with pytest.raises(BudgetExceeded):
        asyncio.run(llm("hi"))
    assert db.snapshot()["physical_attempts"] <= 3
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_cumulative_token_cap(tmp_path):
    db = BudgetDB(tmp_path / "e.sqlite", max_physical=100, max_cost_usd=5.0)
    # shrink cumulative output tokens to 1000 (= 2 requests of 500)
    with db._lock:
        db._conn.execute("UPDATE budget SET max_tokens_out=1000 WHERE id=1")
        db._conn.commit()
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_input_tokens=2000, max_output_tokens=500)
    asyncio.run(llm("a"))
    asyncio.run(llm("b"))
    with pytest.raises(BudgetExceeded):
        asyncio.run(llm("c"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_concurrent_cannot_break_caps(tmp_path):
    db = BudgetDB(tmp_path / "f.sqlite", max_physical=4, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger)
    errors = []

    def worker():
        for _ in range(3):
            try:
                asyncio.run(llm("hi"))
            except Exception as e:
                errors.append(type(e).__name__)

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    snap = db.snapshot()
    assert snap["physical_attempts"] <= snap["max_physical"]
    assert "BudgetExceeded" in errors
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_restart_keeps_token_and_cost_caps(tmp_path):
    path = tmp_path / "g.sqlite"
    db = BudgetDB(path, max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger)
    asyncio.run(llm("a"))
    snap1 = db.snapshot()
    db.close()

    db2 = BudgetDB(path, max_physical=10, max_cost_usd=5.0)
    snap2 = db2.snapshot()
    assert snap2["spent_cost_usd"] == pytest.approx(snap1["spent_cost_usd"])
    assert snap2["tokens_in"] == snap1["tokens_in"]
    assert snap2["tokens_out"] == snap1["tokens_out"]
    install_global_gate(None, strict=False)
    provider.shutdown()
    db2.close()


# ---------------- unknown billing fail-closed ----------------

def test_timeout_blocks_billing(tmp_path):
    db = BudgetDB(tmp_path / "h.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="timeout")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=1.0)
    with pytest.raises(Exception):
        asyncio.run(llm("hello"))
    assert db.is_billing_blocked()
    rows = ledger.rows()
    assert rows and rows[0]["request_status"] == "fail_closed"
    with pytest.raises(BillingBlocked):
        asyncio.run(llm("hello"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_missing_usage_blocks_billing(tmp_path):
    db = BudgetDB(tmp_path / "i.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="missing_usage")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger)
    with pytest.raises(Exception):
        asyncio.run(llm("hello"))
    assert db.is_billing_blocked()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_500_uncertain_billing_blocks(tmp_path):
    db = BudgetDB(tmp_path / "j.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="http_500")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger)
    with pytest.raises(Exception):
        asyncio.run(llm("hello"))
    # uncertain billing after a real send -> must NOT allow free continuation
    assert db.is_billing_blocked()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------- structured output fail-closed ----------------

def _llm_with_raw(env, raw: str):
    llm = env["llm"]
    llm._http_chat = lambda prompt: (raw, 200, 10, 5)  # type: ignore
    return llm


def test_valid_structured_response_accepted(env):
    raw = (
        "<modification>add operator</modification>\n"
        "<graph>class Workflow:\n    async def __call__(self, problem):\n        return 'ans'</graph>\n"
        "<prompt>INSTRUCTION = 'v1'</prompt>"
    )
    llm = _llm_with_raw(env, raw)
    out = asyncio.run(llm.call_with_format("optimize"))
    assert out["modification"] == "add operator"
    assert "class Workflow" in out["graph"]
    assert out["prompt"] == "INSTRUCTION = 'v1'"


def test_malformed_response_rejected(env):
    llm = _llm_with_raw(env, "this is not structured at all")
    with pytest.raises(StructuredOutputError):
        asyncio.run(llm.call_with_format("optimize"))


def test_missing_graph_rejected(env):
    raw = "<modification>m</modification><prompt>p</prompt>"
    llm = _llm_with_raw(env, raw)
    with pytest.raises(StructuredOutputError, match="MISSING_GRAPH"):
        asyncio.run(llm.call_with_format("optimize"))


def test_missing_prompt_rejected(env):
    raw = "<modification>m</modification><graph>class Workflow:\n    pass</graph>"
    llm = _llm_with_raw(env, raw)
    with pytest.raises(StructuredOutputError, match="MISSING_PROMPT"):
        asyncio.run(llm.call_with_format("optimize"))


def test_invalid_python_rejected(env):
    raw = (
        "<modification>m</modification>"
        "<graph>class Workflow:\n    def broken(:\n        pass</graph>"
        "<prompt>p</prompt>"
    )
    llm = _llm_with_raw(env, raw)
    with pytest.raises(StructuredOutputError, match="INVALID_PYTHON"):
        asyncio.run(llm.call_with_format("optimize"))


def test_missing_workflow_class_rejected(env):
    raw = "<modification>m</modification><graph>def f(): return 1</graph><prompt>p</prompt>"
    llm = _llm_with_raw(env, raw)
    with pytest.raises(StructuredOutputError, match="MISSING_WORKFLOW_CLASS"):
        asyncio.run(llm.call_with_format("optimize"))


def test_no_synthetic_success_fallback(env):
    """The old default {'modification': 'gateway-mod', ...} must be gone."""
    src = (ROOT / "src" / "runtime" / "provider_gateway.py").read_text(encoding="utf-8")
    assert "gateway-mod" not in src
    assert "INSTRUCTION = 'gw'" not in src
