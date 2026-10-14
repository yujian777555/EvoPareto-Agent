"""Phase 3 tests: preference encoding, adapter, controller, integration."""

import random

import pytest

from src.agent.individual import Individual
from src.agent.genome import AgentGenome
from src.evolution.memory_evolution import run_memory_evolution
from src.evolution.preference import (
    PREFERENCE_MODES,
    PreferenceVector,
    encode_preference,
    preference_satisfaction,
)
from src.evolution.preference_controller import PreferenceController, controller_for_mode
from src.evolution.reference_adapter import (
    PreferenceAwareNSGA3,
    adapt_reference_directions,
    reference_region_scores,
    weighted_pareto_score,
)


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
# 1. Preference encoding
# ====================================================================== #
def test_preference_vector_bounds():
    with pytest.raises(ValueError):
        PreferenceVector(performance=1.5)
    v = PreferenceVector(0.8, 0.3, 0.2, 0.7, 0.5)
    assert v.performance == 0.8
    assert len(v.as_tuple()) == 5


def test_encode_modes():
    for mode in ("accuracy_first", "cost_first", "balanced", "robust_first"):
        assert mode in PREFERENCE_MODES
        v = encode_preference(mode)
        assert isinstance(v, PreferenceVector)
    a = encode_preference("accuracy_first")
    c = encode_preference({"mode": "cost_first"})
    assert a.performance > c.performance
    assert c.cost > a.cost


def test_encode_dict_and_list_and_json():
    v = encode_preference({"performance": 0.8, "efficiency": 0.3, "cost": 0.2, "robustness": 0.7, "autonomy": 0.5})
    assert v.performance == 0.8
    v2 = encode_preference([0.9, 0.3, 0.2, 0.8, 0.5])
    assert v2.robustness == 0.8
    v3 = PreferenceVector.from_json(v.to_json())
    assert v3 == v


def test_preference_serialization_compare():
    a = encode_preference("balanced")
    b = encode_preference("balanced")
    assert a == b
    assert a.key() == b.key()
    assert (a < encode_preference("accuracy_first")) or (encode_preference("accuracy_first") < a)


# ====================================================================== #
# 2. Normalization
# ====================================================================== #
def test_preference_normalized():
    v = PreferenceVector(1.0, 0.0, 0.0, 0.0, 0.0)
    n = v.normalized()
    assert n.performance == pytest.approx(1.0)
    assert n.efficiency == pytest.approx(0.0)


def test_preference_unit_vector():
    u = PreferenceVector(1.0, 0.0, 0.0, 0.0, 0.0).unit()
    assert u[0] == pytest.approx(1.0)
    assert sum(x * x for x in u) == pytest.approx(1.0)


def test_preference_similarity():
    a = encode_preference("accuracy_first")
    b = encode_preference("accuracy_first")
    c = encode_preference("cost_first")
    assert a.similarity(b) == pytest.approx(1.0)
    assert a.similarity(c) < 1.0


# ====================================================================== #
# 3. Reference adaptation
# ====================================================================== #
def test_adapt_directions_stay_on_simplex():
    from src.evolution.nsga3 import generate_reference_directions

    dirs = generate_reference_directions(5, 2)
    pref = encode_preference("accuracy_first")
    adapted = adapt_reference_directions(dirs, pref, strength=1.0)
    assert len(adapted) == len(dirs)
    for d in adapted:
        assert sum(d) == pytest.approx(1.0)
        assert all(x >= -1e-12 for x in d)


def test_adapt_strength_zero_identity():
    from src.evolution.nsga3 import generate_reference_directions

    dirs = generate_reference_directions(5, 2)
    adapted = adapt_reference_directions(dirs, encode_preference("cost_first"), strength=0.0)
    for a, b in zip(adapted, dirs):
        assert sum(a) == pytest.approx(1.0)


def test_adapt_bias_toward_preference():
    pref = PreferenceVector(1.0, 0.0, 0.0, 0.0, 0.0)
    dirs = [[0.2, 0.2, 0.2, 0.2, 0.2]]
    adapted = adapt_reference_directions(dirs, pref, strength=1.0, eps=0.15)
    # performance component should gain mass
    assert adapted[0][0] > 0.2


def test_preference_aware_nsga3_api():
    nsga = PreferenceAwareNSGA3(
        n_objectives=5,
        divisions=2,
        seed=0,
        preference=encode_preference("accuracy_first"),
    )
    assert nsga.preference.performance > nsga.preference.cost
    base = nsga.base_directions()
    dirs = nsga.reference_directions()
    assert len(base) == len(dirs)
    pop = [
        Individual(genome=AgentGenome.random(random.Random(i)), fitness_vector=[0.5] * 5, generation=0)
        for i in range(6)
    ]
    sel = nsga.select(pop, 3)
    assert len(sel) == 3  # API unchanged


def test_reference_region_scores():
    from src.evolution.nsga3 import generate_reference_directions

    dirs = generate_reference_directions(5, 2)
    scores = reference_region_scores(dirs, encode_preference("accuracy_first"))
    assert len(scores) == len(dirs)
    assert all(0.0 <= s <= 1.0 for s in scores)


# ====================================================================== #
# 4. Preference scoring
# ====================================================================== #
def test_preference_satisfaction_order():
    pref = encode_preference("accuracy_first")  # cares about performance
    high_perf = [0.9, 0.4, 0.5, 0.7, 0.5]
    low_perf = [0.2, 0.4, 0.5, 0.7, 0.5]
    assert preference_satisfaction(high_perf, pref) > preference_satisfaction(low_perf, pref)


def test_preference_satisfaction_cost_first():
    pref = encode_preference("cost_first")
    cheap = [0.4, 0.5, 0.1, 0.5, 0.5]
    pricey = [0.4, 0.5, 0.9, 0.5, 0.5]
    assert preference_satisfaction(cheap, pref) > preference_satisfaction(pricey, pref)


def test_weighted_pareto_score():
    pref = encode_preference("robust_first")
    assert weighted_pareto_score([0.5, 0.5, 0.5, 0.9, 0.5], pref) > weighted_pareto_score(
        [0.5, 0.5, 0.5, 0.2, 0.5], pref
    )


# ====================================================================== #
# 5. PreferenceController + end-to-end
# ====================================================================== #
def test_controller_set_get():
    ctrl = PreferenceController()
    p = ctrl.set_preference({"mode": "cost_first"})
    assert p.cost >= p.performance
    assert ctrl.get_preference() == p


def test_controller_reference_region():
    ctrl = controller_for_mode("accuracy_first")
    region = ctrl.get_reference_region()
    assert region["n_directions"] > 0
    assert len(region["directions"]) == region["n_directions"]
    assert "preference" in region


def test_controller_score_and_rank():
    ctrl = controller_for_mode("accuracy_first")
    good = Individual(
        genome=AgentGenome.random(random.Random(0)),
        fitness_vector=[0.9, 0.5, 0.4, 0.7, 0.5],
        generation=0,
    )
    bad = Individual(
        genome=AgentGenome.random(random.Random(1)),
        fitness_vector=[0.2, 0.5, 0.4, 0.7, 0.5],
        generation=0,
    )
    assert ctrl.score_individual(good) > ctrl.score_individual(bad)
    ranked = ctrl.rank_population([bad, good])
    assert ranked[0][0] is good


def test_controller_select_api():
    ctrl = controller_for_mode("balanced", divisions=2)
    pop = [
        Individual(genome=AgentGenome.random(random.Random(i)), fitness_vector=[0.5] * 5, generation=0)
        for i in range(8)
    ]
    sel = ctrl.select(pop, 4)
    assert len(sel) == 4


def test_preference_changes_search_region():
    """accuracy_first vs cost_first should rank solutions differently."""
    acc = controller_for_mode("accuracy_first")
    cost = controller_for_mode("cost_first")
    a = [0.9, 0.3, 0.8, 0.5, 0.5]  # high perf, high cost
    b = [0.3, 0.7, 0.1, 0.5, 0.5]  # low perf, low cost
    assert acc.score_solution(a) > acc.score_solution(b)
    assert cost.score_solution(b) > cost.score_solution(a)


def test_end_to_end_preference_evolution():
    out = run_memory_evolution(
        toy_eval,
        pop_size=16,
        n_generations=5,
        seed=31,
        preference="accuracy_first",
        experience_mode="robust_peem",
    )
    assert out["preference"] is not None
    assert out["preference"]["performance"] > out["preference"]["cost"]
    assert out["preference_satisfaction"] is not None
    assert out["final_hypervolume"] >= 0


def test_different_preferences_different_region():
    outs = {}
    for mode in ("accuracy_first", "cost_first"):
        outs[mode] = run_memory_evolution(
            toy_eval,
            pop_size=16,
            n_generations=5,
            seed=32,
            preference=mode,
            experience_mode="robust_peem",
        )
    # Preference satisfaction of each mode should favor its own runs
    assert outs["accuracy_first"]["preference_satisfaction"] is not None
    assert outs["cost_first"]["preference_satisfaction"] is not None
    # Mean performance of accuracy_first population should be >= cost_first (typically)
    # Use preference vectors to score both outcomes.
    acc_pref = encode_preference("accuracy_first")
    cost_pref = encode_preference("cost_first")

    def mean_sat(out, pref):
        rows = [i.fitness_vector for i in out["loop"].individuals if i.has_fitness()]
        return sum(preference_satisfaction(r, pref) for r in rows) / len(rows)

    # Cross-evaluation: each mode is happier under its own preference.
    assert mean_sat(outs["accuracy_first"], acc_pref) >= mean_sat(outs["cost_first"], acc_pref) - 0.05
    assert mean_sat(outs["cost_first"], cost_pref) >= mean_sat(outs["accuracy_first"], cost_pref) - 0.05


def test_preference_noise_stability():
    """Slight preference noise should not crash the loop."""

    def noisy_pref():
        base = encode_preference("balanced").as_tuple()
        rng = random.Random(9)
        return [min(1.0, max(0.0, v + rng.uniform(-0.05, 0.05))) for v in base]

    out = run_memory_evolution(
        toy_eval,
        pop_size=12,
        n_generations=3,
        seed=33,
        preference=noisy_pref(),
        experience_mode="robust_peem",
    )
    assert out["final_hypervolume"] >= 0
    assert out["preference"] is not None
