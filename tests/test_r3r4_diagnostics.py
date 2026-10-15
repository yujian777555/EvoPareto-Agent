"""Phase5-R3-R4 tests: budget gate, tokens, objective counterexamples, progress."""

import threading

import pytest

from src.evaluation.objective_diagnostics import (
    autonomy_from_behavior,
    cost_resolution,
    efficiency_conditional_candidate,
    efficiency_counterexamples,
    full_audit_table,
    robustness_redundancy,
)
from src.evaluation.progress_signals import classify_failure, count_repeated_actions, progress_signals
from src.runtime.api_budget import APICallGate, BudgetExceeded


class FakeResp:
    def __init__(self, text="OK", pin=10, pout=2, cost=0.0001):
        self.text = text
        self.tokens_prompt = pin
        self.tokens_completion = pout
        self.cost = cost


def test_budget_hard_gate_before_request():
    calls = []

    def backend(prompt, budget=32, **k):
        calls.append(1)
        return FakeResp()

    gate = APICallGate(backend, max_calls=3, max_cost_usd=10.0)
    for _ in range(3):
        gate.generate("hi")
    with pytest.raises(BudgetExceeded):
        gate.generate("hi")
    assert len(calls) == 3
    assert gate.ledger.requests_ok == 3


def test_retry_consumes_budget():
    n = {"i": 0}

    def backend(prompt, budget=32, **k):
        n["i"] += 1
        if n["i"] < 3:
            raise RuntimeError("fail")
        return FakeResp()

    gate = APICallGate(backend, max_calls=3, max_cost_usd=10.0, max_retries=2)
    resp = gate.generate("hi")
    assert resp.text == "OK"
    assert gate.ledger.retries == 2
    assert gate.ledger.requests_failed == 2
    assert gate.ledger.requests_ok == 1


def test_failed_request_still_counts():
    def backend(prompt, budget=32, **k):
        raise RuntimeError("down")

    gate = APICallGate(backend, max_calls=2, max_cost_usd=10.0, max_retries=1)
    with pytest.raises(RuntimeError):
        gate.generate("hi")
    snap = gate.snapshot()
    assert snap["requests_failed"] == 2  # original + retry
    with pytest.raises(BudgetExceeded):
        gate.generate("hi")


def test_actual_tokens_from_usage_not_textlen():
    def backend(prompt, budget=32, **k):
        return FakeResp(text="x" * 1000, pin=77, pout=88, cost=0.002)

    gate = APICallGate(backend, max_calls=5, max_cost_usd=1.0)
    gate.generate("short")
    led = gate.ledger.to_dict()
    assert led["actual_in"] == 77
    assert led["actual_out"] == 88
    assert led["estimated_in"] > 0  # reserve estimate exists
    assert led["actual_total_tokens"] == 165


def test_concurrent_budget_never_exceeds():
    ok = []
    lock = threading.Lock()

    def backend(prompt, budget=32, **k):
        return FakeResp()

    gate = APICallGate(backend, max_calls=20, max_cost_usd=50.0)

    def worker():
        for _ in range(10):
            try:
                gate.generate("p")
                with lock:
                    ok.append(1)
            except BudgetExceeded:
                pass

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    snap = gate.snapshot()
    assert snap["requests_ok"] + snap["requests_failed"] <= 20
    assert snap["reserved_calls"] == 0


# --- objective diagnostics ---
def test_quick_fail_efficiency_warning():
    ex = efficiency_counterexamples(20)
    assert ex["quick_fail_1step"] > ex["serious_fail_10step"]
    assert ex["quick_fail_beats_serious_try"] is True


def test_candidate_efficiency_penalizes_fail():
    fail = efficiency_conditional_candidate(False, 1, 20, 20)
    success = efficiency_conditional_candidate(True, 12, 500, 20)
    assert fail < success


def test_robustness_zero_when_perf_zero():
    r = robustness_redundancy(0.0, 0.5)
    assert r["robustness_current"] == 0.0
    assert r["identical_when_perf_zero"] is True


def test_autonomy_from_behavior_not_genome_name():
    a = autonomy_from_behavior(10, 0, 0)
    b = autonomy_from_behavior(10, 5, 2)
    assert a == 1.0
    assert b < a


def test_cost_resolution_small_range():
    r = cost_resolution([0.001, 0.002])
    assert r["saturating_range"] < 0.01


def test_audit_table_flags_invalid():
    rows = full_audit_table()
    by = {r["objective"]: r for r in rows}
    assert by["efficiency"]["valid"] is False
    assert by["robustness"]["valid"] is False
    assert by["autonomy"]["valid"] is False
    assert by["performance"]["valid"] is True


# --- progress / failure taxonomy ---
def test_failure_taxonomy():
    assert classify_failure("budget_exhausted", False) == "budget_exhausted"
    assert classify_failure("won", True) == "task_success"
    assert classify_failure("max_steps", False) == "max_steps"


def test_progress_signals():
    traj = [
        {"obs": "You see a vase 1.", "action": "take vase 1"},
        {"obs": "You take the vase 1.", "action": "open safe 1"},
        {"obs": "You open the safe 1.", "action": "go to table 1"},
        {"obs": "You arrive at table 1.", "action": "go to table 1"},
    ]
    p = progress_signals(traj, "put a vase in safe")
    assert p["found_goal_object"] is True
    assert p["picked_something"] is True
    assert p["opened_container"] is True
    assert p["repeated_actions"] >= 1


def test_count_repeated_actions():
    t = [{"action": "look"}, {"action": "look"}, {"action": "go x"}]
    assert count_repeated_actions(t) == 1
