"""Phase5-R3-R5 tests: budget settlement, physical count, objectives, 2D NSGA."""

import threading

import pytest

from src.evaluation.objective_diagnostics import efficiency_counterexamples
from src.runtime.api_budget import (
    APICallGate,
    BillingBlocked,
    BudgetExceeded,
    bump_physical_http,
    physical_http_count,
    reset_physical_http,
)


class _Resp:
    def __init__(self, pin=10, pout=2, cost=0.001):
        self.text = "OK"
        self.tokens_prompt = pin
        self.tokens_completion = pout
        self.cost = cost
        self.model = "deepseek-flash"


def test_reserved_cost_released_on_success():
    def backend(prompt, budget=32, **k):
        return _Resp()

    gate = APICallGate(backend, max_calls=10, max_cost_usd=1.0)
    for _ in range(5):
        gate.generate("hi")
    snap = gate.snapshot()
    assert snap["reserved_calls"] == 0
    assert snap["reserved_cost_usd"] == 0.0
    assert snap["pending_reservations"] == 0
    gate.assert_clean_shutdown()


def test_reserved_cost_released_on_failure():
    def backend(prompt, budget=32, **k):
        raise RuntimeError("timeout")

    gate = APICallGate(backend, max_calls=10, max_cost_usd=1.0, max_retries=1)
    with pytest.raises(RuntimeError):
        gate.generate("hi")
    snap = gate.snapshot()
    assert snap["reserved_calls"] == 0
    assert snap["reserved_cost_usd"] == 0.0


def test_reserved_cost_released_on_402():
    def backend(prompt, budget=32, **k):
        raise RuntimeError("status=402 Payment Required")

    gate = APICallGate(backend, max_calls=5, max_cost_usd=1.0, max_retries=3)
    with pytest.raises(BillingBlocked):
        gate.generate("x")
    assert gate.snapshot()["reserved_cost_usd"] == 0.0


def test_concurrent_reserve_settle_consistency():
    def backend(prompt, budget=32, **k):
        return _Resp()

    gate = APICallGate(backend, max_calls=30, max_cost_usd=10.0)

    def worker():
        for _ in range(8):
            try:
                gate.generate("p")
            except BudgetExceeded:
                pass

    ts = [threading.Thread(target=worker) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    gate.assert_clean_shutdown()
    assert gate.snapshot()["requests_ok"] <= 30


def test_physical_http_counter_increments():
    reset_physical_http()
    bump_physical_http()
    bump_physical_http()
    assert physical_http_count() == 2


def test_logical_vs_physical_can_differ():
    # one logical call may map to >1 physical attempts via transport retries
    reset_physical_http()
    n = {"c": 0}

    def flaky(prompt, budget=32, **k):
        n["c"] += 1
        bump_physical_http()
        if n["c"] == 1:
            raise RuntimeError("timeout")
        return _Resp()

    gate = APICallGate(flaky, max_calls=10, max_cost_usd=1.0, max_retries=2)
    gate.generate("p")
    snap = gate.snapshot()
    assert snap["requests_ok"] == 1
    assert physical_http_count() >= 2  # fail + success physical attempts
    assert snap["reserved_cost_usd"] == 0.0


def test_persistent_ledger_roundtrip(tmp_path):
    path = tmp_path / "budget.json"

    def backend(prompt, budget=32, **k):
        return _Resp(cost=0.01)

    g1 = APICallGate(backend, max_calls=10, max_cost_usd=1.0, ledger_path=str(path))
    g1.generate("a")
    g1.generate("b")
    g2 = APICallGate(backend, max_calls=10, max_cost_usd=1.0, ledger_path=str(path))
    assert g2.ledger.requests_ok == 2
    assert g2.spent_cost == pytest.approx(0.02)


# --- objective construction cases ---
def test_efficiency_counterexample_still_true():
    ex = efficiency_counterexamples(20)
    assert ex["quick_fail_beats_success"] is True


def test_two_obj_dominance_cost_min():
    # success up, cost down dominates
    a = (0.9, 0.1)  # success, cost
    b = (0.5, 0.2)

    def dominates(x, y):
        return (
            x[0] >= y[0]
            and x[1] <= y[1]
            and (x[0] > y[0] or x[1] < y[1])
        )

    assert dominates(a, b)
    assert not dominates(b, a)


def test_nsga3_2d_reference_directions():
    from src.evolution.nsga3 import generate_reference_directions

    dirs = generate_reference_directions(2, divisions=4)
    assert len(dirs) == 5  # C(4+2-1, 2-1) = 5
    for d in dirs:
        assert abs(sum(d) - 1.0) < 1e-9


def test_candidate_evaluator_versions_distinct():
    # ensure we do not silently replace legacy
    from src.evaluation import objective_diagnostics as od

    assert hasattr(od, "full_audit_table")


def test_no_proxy_results_in_native_tables():
    # guard: native evaluator path must not import proxy scorer
    import inspect

    import src.evaluation.native_evolution_evaluator as nev

    src = inspect.getsource(nev)
    assert "_score_completion" not in src
    assert "genome_capability" not in src.lower()
    assert "PLANNER_CAP" not in src
