"""Math contract tests: 2-objective direction (performance↑, cost↓)."""
from __future__ import annotations

import pytest


def test_objective_direction_contracts():
    from src.evaluation.metrics import hypervolume
    from src.evolution.credit_assignment import compute_credit, CreditWeights
    from src.evolution.pareto_experience import ParetoExperience
    from src.evolution.pareto_credit import contribution_from_improvement_and_ranks

    # higher performance better: p=0.9 should beat p=0.1 at same cost
    # cost lower better: c=0.1 beats c=0.5 at same performance

    # hypervolume in minimization space (to_minimization of [perf, cost] with max/min)
    from src.evaluation.objectives import to_minimization
    # paper semantics: [performance maximize, cost minimize]
    a = to_minimization([0.9, 0.1], maximize=[True, False])
    b = to_minimization([0.1, 0.1], maximize=[True, False])
    # a dominates b in min-space (both coords smaller after flip)
    assert a[0] < b[0]
    assert a[1] == pytest.approx(b[1])

    # same perf, higher cost is worse
    c1 = to_minimization([0.8, 0.1], maximize=[True, False])
    c2 = to_minimization([0.8, 0.5], maximize=[True, False])
    assert c1[1] < c2[1]

    # credit improvement: better child should score positive
    pe = ParetoExperience()
    v_good = pe.update("m1", parent_objectives=[0.5, 0.4], child_objectives=[0.8, 0.3])
    v_bad = pe.update("m2", parent_objectives=[0.5, 0.4], child_objectives=[0.2, 0.6])
    assert v_good > v_bad
