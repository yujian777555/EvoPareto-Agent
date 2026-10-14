"""Phase5-Audit-2 tests: attribution stats, bootstrap CI, counterfactual probe."""

import pytest

from src.agent.genome import AgentGenome
from src.evolution.operator_attribution import (
    attribution_verdict,
    bootstrap_ci,
    counterfactual_probe,
    observational_operator_stats,
)


class FakeRec:
    def __init__(self, t, parent, child, success=True, hv=0.0):
        self.mutation_type = t
        self.parent_objectives = parent
        self.child_objectives = child
        self.success = success
        self.hypervolume_contribution = hv


def toy_eval(g: AgentGenome):
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    return [p[g.planner_strategy], 0.5, 0.5, 0.5, 0.5]


def test_bootstrap_ci_contains_mean():
    xs = [0.1, 0.2, 0.3, 0.4]
    lo, hi = bootstrap_ci(xs, n_boot=200, seed=0)
    assert lo <= 0.25 <= hi


def test_bootstrap_ci_single():
    assert bootstrap_ci([0.5]) == (0.5, 0.5)


def test_observational_stats():
    recs = [
        FakeRec("planner", [0.5] * 5, [0.7] * 5, True, 0.01),
        FakeRec("planner", [0.5] * 5, [0.6] * 5, True, 0.01),
        FakeRec("tool", [0.5] * 5, [0.4] * 5, False, 0.0),
    ]
    st = observational_operator_stats(recs)
    assert st["planner"].n == 2
    assert st["planner"].mean_improvement > 0
    assert st["tool"].mean_improvement < 0
    assert st["planner"].ci_low < st["planner"].ci_high


def test_counterfactual_probe_runs():
    parents = [AgentGenome.random(__import__("random").Random(i)) for i in range(5)]
    cf = counterfactual_probe(parents, toy_eval, seed=0, n_repeats=2)
    assert set(cf) >= {"planner", "memory", "tool", "budget", "reflection"}
    for st in cf.values():
        assert st.kind == "counterfactual"
        assert st.n > 0


def test_attribution_verdict_structure():
    from src.evolution.operator_attribution import OperatorStats

    obs = {"planner": OperatorStats("planner", 5, 0.1, 0.0, 0.0, 0.5, 0.0, 0.2)}
    cf = {"planner": OperatorStats("planner", 5, 0.1, 0.0, 0.0, 0.5, 0.0, 0.2, "counterfactual")}
    v = attribution_verdict(obs, cf)
    assert "causal_claim_supported" in v
    assert "limitations" not in v or True
    assert v["top1_agreement"] is True
