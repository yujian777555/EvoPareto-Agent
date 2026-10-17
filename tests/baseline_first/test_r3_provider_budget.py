"""Provider response path + budget hard-cap tests (R3 Task B/C)."""
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
    MockHTTPProvider,
    RequestLedger,
    StructuredOutputError,
    conservative_input_tokens,
    mock_chat_completion_body,
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
        base_url=provider.base_url, ledger=ledger, run_id="r3",
        max_input_tokens=8000, max_output_tokens=500, timeout=6.0,
    )
    yield {"db": db, "llm": llm, "ledger": ledger, "provider": provider}
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------- Task B: provider-returned responses ----------------

def test_provider_serves_task_answer_body():
    body = mock_chat_completion_body("Solve: What is 3+4?")
    assert "choices" in body and body["usage"]["prompt_tokens"] > 0
    content = body["choices"][0]["message"]["content"]
    assert "####" in content
    # gold-blind: derived from question numbers, not a hidden gold
    assert "3" in content or "4" in content


def test_provider_serves_mutation_xml_body():
    body = mock_chat_completion_body("GraphOptimize this workflow")
    content = body["choices"][0]["message"]["content"]
    assert "<modification>" in content
    assert "<graph>" in content and "class Workflow" in content
    assert "<prompt>" in content


def test_http_200_valid_roundtrip_no_override(env):
    """GatewayLLM must return the PROVIDER body, not a local replacement."""
    llm = env["llm"]
    out = asyncio.run(llm("Solve: What is 9+1?"))
    # provider derived '9' as first number in the question
    assert "#### 9" in out or "#### 1" in out
    # the mock provider saw a real HTTP POST
    assert env["provider"].requests_seen
    body = env["provider"].requests_seen[-1]["body"]
    msgs = body.get("messages") or []
    assert any("Solve: What is 9+1?" in str(m.get("content", "")) for m in msgs)


def test_structured_mutation_from_provider(env):
    llm = env["llm"]
    parsed = asyncio.run(llm.call_with_format("GraphOptimize please"))
    assert parsed["modification"]
    assert "class Workflow" in parsed["graph"]
    assert parsed["prompt"]


def test_http_200_invalid_json_rejected(tmp_path):
    db = BudgetDB(tmp_path / "ij.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="invalid_json")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    assert ledger.rows() and ledger.rows()[0]["request_status"] in ("failed", "fail_closed")
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_200_missing_usage_fail_closed(tmp_path):
    db = BudgetDB(tmp_path / "mu.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="missing_usage")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    assert db.is_billing_blocked()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_200_malformed_xml_rejected(tmp_path):
    db = BudgetDB(tmp_path / "mx.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="malformed_xml")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(StructuredOutputError):
        asyncio.run(llm.call_with_format("GraphOptimize"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_429_recorded(tmp_path):
    db = BudgetDB(tmp_path / "e429.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="http_429")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    assert ledger.rows()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_500_fail_closed(tmp_path):
    db = BudgetDB(tmp_path / "e5.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="http_500")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    assert db.is_billing_blocked()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_http_timeout_fail_closed(tmp_path):
    db = BudgetDB(tmp_path / "to.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="timeout")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=1.0)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    assert db.is_billing_blocked() or ledger.rows()
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_empty_response_rejected(tmp_path):
    db = BudgetDB(tmp_path / "em.sqlite", max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider(scenario="empty")
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, timeout=5)
    with pytest.raises(Exception):
        asyncio.run(llm("hi"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


# ---------------- Task B3: ledger reconciliation ----------------

def test_ledger_reconciles_with_http(env):
    llm = env["llm"]
    asyncio.run(llm("Solve: 1+1"))
    asyncio.run(llm("GraphOptimize"))
    rows = env["ledger"].rows()
    assert len(rows) == len(env["provider"].requests_seen)
    for r in rows:
        assert r["logical_request_id"]
        assert r["physical_request_id"]
        assert r["model"] == "deepseek-flash"
        assert r["reserved_cost"] is not None
        assert r["request_status"] in ("settled_ok", "failed", "fail_closed")
        assert r["reported_tokens_in"] is not None or r["request_status"] != "settled_ok"


# ---------------- Task C: 8000/500 budget ----------------

def test_worst_case_8000_500_is_0_003():
    w = worst_case_cost("deepseek-flash", 8000, 500)
    assert w == pytest.approx(8000 * 0.30 / 1e6 + 500 * 1.20 / 1e6)
    assert w == pytest.approx(0.003)


def test_reservations_sum_under_5usd_for_300_requests():
    per = worst_case_cost("deepseek-flash", 8000, 500)
    assert 300 * per < 5.00


def test_reservation_covers_max_allowed_tokens(env):
    llm = env["llm"]
    prompt = "x" * 100
    asyncio.run(llm(prompt))
    row = env["ledger"].rows()[0]
    est_in = conservative_input_tokens(prompt)
    expected = worst_case_cost("deepseek-flash", est_in, 500)
    assert row["reserved_cost"] == pytest.approx(expected)


def test_input_over_8000_rejected(env):
    llm = env["llm"]
    with pytest.raises(Exception):
        asyncio.run(llm("y" * 9000))
    assert not env["provider"].requests_seen


def test_cumulative_input_tokens_exhausted(tmp_path):
    db = BudgetDB(tmp_path / "ci.sqlite", max_physical=100, max_cost_usd=5.0)
    with db._lock:
        db._conn.execute("UPDATE budget SET max_tokens_in=10 WHERE id=1")
        db._conn.commit()
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_input_tokens=8000, max_output_tokens=500)
    with pytest.raises(BudgetExceeded):
        asyncio.run(llm("hello world this is long enough"))
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_concurrency_cannot_break_300_cap(tmp_path):
    db = BudgetDB(tmp_path / "cc.sqlite", max_physical=5, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_input_tokens=8000, max_output_tokens=500)
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
    assert db.snapshot()["physical_attempts"] <= 5
    assert "BudgetExceeded" in errors
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


def test_restart_keeps_consumption(tmp_path):
    path = tmp_path / "rs.sqlite"
    db = BudgetDB(path, max_physical=10, max_cost_usd=5.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, max_input_tokens=8000, max_output_tokens=500)
    asyncio.run(llm("a"))
    snap1 = db.snapshot()
    db.close()
    db2 = BudgetDB(path, max_physical=10, max_cost_usd=5.0)
    snap2 = db2.snapshot()
    assert snap2["physical_attempts"] == snap1["physical_attempts"]
    assert snap2["spent_cost_usd"] == pytest.approx(snap1["spent_cost_usd"])
    install_global_gate(None, strict=False)
    provider.shutdown()
    db2.close()


def test_optimizer_prompt_len_vs_8000():
    p = ROOT / "results" / "stage3_0_p1_r2a_r3" / "official_aflow_full_mock_trace.json"
    if not p.exists():
        pytest.skip("run e2e first")
    e = json.loads(p.read_text(encoding="utf-8"))["events"]
    mx = e.get("PROMPT_LENGTH_MAX") or 0
    if mx > 8000:
        pytest.fail(f"optimizer prompt {mx} exceeds 8000 cap — no silent truncation allowed")
    assert mx <= 8000
