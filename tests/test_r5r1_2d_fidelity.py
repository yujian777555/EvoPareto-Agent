"""Phase5-R3-R5-R1 tests: 2D dominance, PEEM spec, PPEC 2D, NSGA-II, gate."""

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.objective_spec import SPEC_2, SPEC_5, get_spec, assert_same_spec
from src.evolution.credit_assignment import objective_improvement
from src.evolution.nsga2_baseline import NSGA2
from src.evolution.nsga3 import NSGA3, generate_reference_directions, non_dominated_sort
from src.evolution.preference_2d import (
    Preference2DController,
    encode_preference_2d,
    preference_satisfaction_2d,
)
from src.runtime.http_budget import BudgetDB, BudgetExceeded, PhysicalBudgetGate, pre_send_approval, install_global_gate


# --- dominance A/B/C/D ---
A = [0.9, 0.10]
B = [0.5, 0.20]
C = [0.9, 0.20]
D = [0.5, 0.05]


def test_2d_dominance_cases():
    assert SPEC_2.dominates(A, B)
    assert SPEC_2.dominates(A, C)
    assert not SPEC_2.dominates(A, D)
    assert not SPEC_2.dominates(D, A)


def test_2d_nsga3_fronts():
    rows = [SPEC_2.to_minimization(x) for x in (A, B, C, D)]
    fronts = non_dominated_sort(rows)
    # A and D non-dominated
    assert set(fronts[0]) == {0, 3}


def test_2d_nsga3_select_respects_maximize():
    inds = []
    for i, row in enumerate((A, B, C, D)):
        g = AgentGenome.random(random_i := __import__("random").Random(i))
        inds.append(Individual(genome=g, fitness_vector=list(row), generation=0))
    nsga = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    sel = nsga.select(inds, 2)
    fits = sorted(tuple(s.fitness_vector) for s in sel)
    assert tuple(A) in fits or tuple(D) in fits
    # B/C should not both be chosen over A
    assert tuple(B) not in fits


def test_cost_is_minimized_not_maximized():
    # lower cost is improvement when success equal
    imp = objective_improvement([0.5, 0.3], [0.5, 0.1], spec=SPEC_2)
    assert imp > 0
    # higher success is improvement when cost equal
    assert objective_improvement([0.5, 0.2], [0.8, 0.2], spec=SPEC_2) > 0


def test_2d_hv_reference():
    from src.evaluation.metrics import hypervolume

    hv = hypervolume([A, D], maximize_input=True)
    assert hv >= 0


def test_nsga2_vs_nsga3_distinct():
    import inspect

    from src.evolution import nsga2_baseline as n2
    from src.evolution import nsga3 as n3

    assert "crowding_distance" in inspect.getsource(n2)
    assert inspect.getsource(n2.NSGA2.select) != inspect.getsource(n3.NSGA3.select)


def test_peem_credit_uses_spec():
    # 2D: cost decrease is positive
    assert objective_improvement([0.5, 0.5], [0.5, 0.2], spec=SPEC_2) > 0
    # 5D legacy still works
    assert objective_improvement([0.5] * 5, [0.6, 0.5, 0.4, 0.5, 0.5], spec=SPEC_5) > 0


def test_spec_dim_mismatch_fail_closed():
    with pytest.raises(ValueError):
        SPEC_2.validate_vector([0.5] * 5)
    with pytest.raises(ValueError):
        assert_same_spec(SPEC_2, SPEC_5)


def test_2d_reference_directions():
    dirs = generate_reference_directions(2, 4)
    assert len(dirs) == 5


def test_ppec_2d_preferences():
    assert encode_preference_2d("success_first").success_w > encode_preference_2d("cost_first").success_w
    s1 = preference_satisfaction_2d(0.9, 0.2, encode_preference_2d("success_first"))
    s2 = preference_satisfaction_2d(0.9, 0.2, encode_preference_2d("cost_first"))
    assert s1 != s2


def test_ppec_2d_selection_differs():
    ctrl_s = Preference2DController("success_first")
    ctrl_c = Preference2DController("cost_first")
    A2 = [0.9, 0.50]
    D2 = [0.5, 0.05]
    rows = [A2, D2]
    assert rows[ctrl_s.select(rows)] == A2
    assert rows[ctrl_c.select(rows)] == D2


def test_ppec_2d_strength_zero_uniform():
    ctrl = Preference2DController("success_first", strength=0.0)
    base = ctrl._base
    assert ctrl.directions == base or all(
        abs(sum(d) - 1.0) < 1e-6 for d in ctrl.directions
    )


def test_ppec_2d_rejects_wrong_dim():
    ctrl = Preference2DController("balanced")
    with pytest.raises((ValueError, IndexError)):
        ctrl.select([[0.5, 0.5, 0.5]])


def test_http_gate_blocks_before_send(tmp_path):
    db = BudgetDB(tmp_path / "b.db", max_calls=2, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate)
    gate.approve()
    gate.release(success=True)
    gate.approve()
    gate.release(success=True)
    with pytest.raises(BudgetExceeded):
        pre_send_approval()  # 3rd send denied BEFORE network
    install_global_gate(None)


def test_sqlite_persistent_across_instances(tmp_path):
    path = tmp_path / "b.db"
    db1 = BudgetDB(path, max_calls=5, max_cost_usd=1.0)
    db1.reserve(0.01)
    db1.settle(0.01, success=True)
    db1.close()
    db2 = BudgetDB(path, max_calls=5, max_cost_usd=1.0)
    assert db2.snapshot()["logical_ok"] == 1
    db2.close()


def test_reserved_released_after_settle(tmp_path):
    db = BudgetDB(tmp_path / "b.db", max_calls=10, max_cost_usd=1.0)
    db.reserve(0.1)
    db.settle(0.1, success=True, actual_cost=0.05)
    snap = db.snapshot()
    assert snap["reserved_calls"] == 0
    assert snap["reserved_cost_usd"] == 0.0
