"""Phase 2.5 tests: PEEM credit, diversity, decay, adaptive probability."""

import math
import random

import pytest

from src.evaluation.metrics import (
    hypervolume,
    igd,
    mutation_entropy,
    normalized_mutation_entropy,
    reference_front_from_population,
)
from src.evolution.adaptive_mutation import AdaptiveMutationController, default_registry
from src.evolution.credit_assignment import (
    CreditWeights,
    compute_credit,
    hypervolume_contribution,
    objective_improvement,
    pareto_rank_change,
    survival_credit,
)
from src.evolution.diversity import (
    crowding_distance,
    diversity_contribution,
    non_dominated_diversity,
    spacing,
)
from src.evolution.pareto_experience import PEEMConfig, ParetoExperience


def toy_eval(genome):
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    e = {"direct": 0.9, "cot": 0.7, "plan_and_solve": 0.55, "tree_search": 0.35, "reflexion": 0.45}
    c = {"no_tools": 0.1, "conservative": 0.3, "balanced": 0.45, "aggressive": 0.7, "tool_first": 0.85}
    t = (genome.reasoning_budget - 8) / 120.0
    return [
        p[genome.planner_strategy] + 0.05 * t,
        e[genome.planner_strategy] - 0.2 * t,
        c[genome.tool_policy] + 0.3 * t,
        0.5 + 0.3 * p[genome.planner_strategy],
        0.5 + 0.2 * e[genome.planner_strategy],
    ]


# ====================================================================== #
# 1. Credit calculation
# ====================================================================== #
def test_objective_improvement_positive_and_negative():
    parent = [0.5, 0.5, 0.5, 0.5, 0.5]
    better = [0.7, 0.6, 0.3, 0.5, 0.5]
    worse = [0.3, 0.4, 0.8, 0.5, 0.5]
    assert objective_improvement(parent, better) > 0
    assert objective_improvement(parent, worse) < 0


def test_pareto_rank_change_sign():
    assert pareto_rank_change(1, 0) == 1
    assert pareto_rank_change(0, 1) == -1
    assert pareto_rank_change(2, 2) == 0


def test_survival_credit_values():
    assert survival_credit(True) == 1.0
    assert survival_credit(False) == 0.0


def test_compute_credit_components_and_mv():
    parent = [0.5, 0.5, 0.5, 0.5, 0.5]
    child = [0.8, 0.5, 0.3, 0.5, 0.5]
    front = [parent]
    br = compute_credit(
        parent,
        child,
        population_front=front,
        parent_rank=1,
        child_rank=0,
        survived=True,
    )
    assert br.improvement > 0
    assert br.survival_credit == 1.0
    assert br.pareto_rank_change == 1
    assert br.mutation_value > 0
    d = br.to_dict()
    assert "mutation_value" in d and "hypervolume_contribution" in d


def test_credit_weights_normalize():
    w = CreditWeights(1, 1, 1, 1).normalized()
    assert w.alpha + w.beta + w.gamma + w.delta == pytest.approx(1.0)


def test_compute_credit_ablation_weights():
    parent = [0.5] * 5
    child = [0.9, 0.9, 0.1, 0.9, 0.9]
    only_hv = CreditWeights(0, 1, 0, 0)
    only_surv = CreditWeights(0, 0, 0, 1)
    a = compute_credit(parent, child, population_front=[parent], weights=only_hv, survived=False)
    b = compute_credit(parent, child, population_front=[parent], weights=only_surv, survived=True)
    assert a.mutation_value != b.mutation_value
    assert b.mutation_value == pytest.approx(1.0)


# ====================================================================== #
# 2. Hypervolume contribution
# ====================================================================== #
def test_hypervolume_contribution_positive_when_improving():
    front = [[0.4, 0.4, 0.6, 0.4, 0.4]]
    child = [0.8, 0.5, 0.4, 0.5, 0.5]
    assert hypervolume_contribution(child, front) > 0


def test_hypervolume_contribution_zero_empty_baseline():
    assert hypervolume_contribution([0.5] * 5, []) >= 0


# ====================================================================== #
# 3. Diversity calculation
# ====================================================================== #
def test_crowding_distance_boundaries_infinite():
    rows = [[0.1, 0.9], [0.5, 0.5], [0.9, 0.1]]
    cd = crowding_distance(rows, maximize_input=False)
    assert math.isinf(cd[0]) and math.isinf(cd[2])
    assert not math.isinf(cd[1])


def test_spacing_metric():
    uniform = [[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]]
    clustered = [[0.0, 1.0], [0.01, 0.99], [1.0, 0.0]]
    assert spacing(uniform, maximize_input=False) < spacing(clustered, maximize_input=False)


def test_diversity_contribution_isolated_point():
    pop = [[0.5, 0.5, 0.5, 0.5, 0.5], [0.51, 0.51, 0.49, 0.51, 0.51]]
    far = [0.9, 0.9, 0.1, 0.9, 0.9]
    assert diversity_contribution(far, pop) > diversity_contribution([0.505] * 5, pop)


def test_non_dominated_diversity():
    rows = [[0.0, 1.0], [1.0, 0.0], [0.5, 0.5], [0.2, 0.2]]
    assert non_dominated_diversity(rows, maximize_input=False) > 0


# ====================================================================== #
# 4. Experience decay
# ====================================================================== #
def test_peem_decay_moves_toward_new_evidence():
    exp = ParetoExperience(PEEMConfig(decay=0.5, prior_value=0.0))
    exp.update(
        "planner",
        parent_objectives=[0.5] * 5,
        child_objectives=[0.2] * 5,  # bad
        survived=False,
    )
    bad_score = exp.get_score("planner")
    exp.update(
        "planner",
        parent_objectives=[0.5] * 5,
        child_objectives=[0.9, 0.9, 0.1, 0.9, 0.9],  # good
        survived=True,
    )
    good_score = exp.get_score("planner")
    assert good_score > bad_score


def test_peem_decay_formula():
    exp = ParetoExperience(PEEMConfig(decay=0.35, prior_value=0.0))
    # Force a known sequence of MVs by monkeypatching compute is heavy;
    # instead verify recursive form: s1 = lam*m1 + (1-lam)*s0
    lam = 0.35
    exp._absorb("tool", 1.0, {})
    s1 = exp.get_score("tool")
    assert s1 == pytest.approx(lam * 1.0 + (1 - lam) * 0.0)
    exp._absorb("tool", 0.0, {})
    s2 = exp.get_score("tool")
    assert s2 == pytest.approx(lam * 0.0 + (1 - lam) * s1)


def test_peem_decay_configurable():
    a = ParetoExperience(PEEMConfig(decay=0.1))
    b = ParetoExperience(PEEMConfig(decay=0.9))
    for exp in (a, b):
        exp._absorb("budget", 1.0, {})
        exp._absorb("budget", 0.0, {})
    # Higher decay reacts more to the latest zero.
    assert b.get_score("budget") < a.get_score("budget")


def test_peem_persistence(tmp_path):
    exp = ParetoExperience(PEEMConfig(decay=0.4))
    exp.update(
        "memory",
        parent_objectives=[0.5] * 5,
        child_objectives=[0.6] * 5,
        survived=True,
    )
    path = tmp_path / "peem.json"
    exp.save_json(path)
    loaded = ParetoExperience.load_json(path)
    assert loaded.get_score("memory") == pytest.approx(exp.get_score("memory"))
    assert loaded.config.decay == pytest.approx(0.4)


# ====================================================================== #
# 5. Adaptive probability (PEEM-aware)
# ====================================================================== #
def test_peem_controller_prefers_high_mv():
    exp = ParetoExperience(PEEMConfig(decay=0.5, prior_value=0.2))
    for _ in range(8):
        exp._absorb("planner", 0.9, {})
        exp._absorb("budget", -0.2, {})
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry(), epsilon=0.0, min_prob=0.0)
    dist = ctrl.probability_distribution()
    assert dist["planner"] > dist["budget"]
    assert sum(dist.values()) == pytest.approx(1.0)


def test_peem_probability_handles_negative_values():
    exp = ParetoExperience(PEEMConfig(decay=1.0, prior_value=0.0))
    for name in default_registry().names():
        exp._absorb(name, -0.5, {})
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry())
    dist = ctrl.probability_distribution()
    assert all(v > 0 for v in dist.values())
    assert sum(dist.values()) == pytest.approx(1.0)


def test_peem_controller_deterministic():
    exp = ParetoExperience()
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry())
    from src.agent.genome import AgentGenome

    g = AgentGenome.random(random.Random(0))
    _, n1 = ctrl.mutate(g, random.Random(7), n_mutations=2)
    _, n2 = ctrl.mutate(g, random.Random(7), n_mutations=2)
    assert n1 == n2


# ====================================================================== #
# Metrics extras
# ====================================================================== #
def test_igd_and_reference_front():
    ref = [[0.0, 1.0], [1.0, 0.0]]
    good = [[0.05, 0.95], [0.95, 0.05]]
    bad = [[0.5, 0.5]]
    assert igd(good, ref, maximize_input=False) < igd(bad, ref, maximize_input=False)
    assert igd([], ref, maximize_input=False) == float("inf")


def test_mutation_entropy_uniform_higher():
    assert mutation_entropy([10, 10, 10, 10]) > mutation_entropy([37, 1, 1, 1])
    assert normalized_mutation_entropy([5, 5]) == pytest.approx(1.0)
    assert normalized_mutation_entropy([10]) == 0.0


def test_reference_front_extraction():
    rows = [[0.9, 0.9, 0.1, 0.9, 0.9], [0.1, 0.1, 0.9, 0.1, 0.1], [0.5, 0.5, 0.5, 0.5, 0.5]]
    front = reference_front_from_population(rows)
    assert len(front) >= 1


# ====================================================================== #
# Integration
# ====================================================================== #
def test_peem_loop_records_survival_and_mv():
    from src.evolution.memory_evolution import run_memory_evolution

    out = run_memory_evolution(
        toy_eval, pop_size=12, n_generations=3, seed=4, use_adaptive=True, experience_mode="peem"
    )
    archive = out["archive"]
    assert len(archive) > 0
    assert any(getattr(r, "mutation_value", 0) != 0 for r in archive)
    exp = out["experience"]
    assert isinstance(exp, ParetoExperience)
    assert any(u.n_updates > 0 for u in exp.utility.values())


def test_peem_vs_phase2_modes():
    from src.evolution.memory_evolution import run_memory_evolution

    peem = run_memory_evolution(
        toy_eval, pop_size=10, n_generations=2, seed=5, experience_mode="peem"
    )
    legacy = run_memory_evolution(
        toy_eval, pop_size=10, n_generations=2, seed=5, experience_mode="phase2"
    )
    assert peem["final_hypervolume"] >= 0 and legacy["final_hypervolume"] >= 0
    assert peem["mutation_probs"] and legacy["mutation_probs"]
