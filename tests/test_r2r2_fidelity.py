"""Phase R2-R2: PEEM 2D credit + PPEC selection that can fail."""

import random

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.objective_spec import SPEC_2
from src.evolution.credit_assignment import compute_credit, objective_improvement
from src.evolution.nsga3 import NSGA3
from src.evolution.pareto_credit import ParetoContributionEstimator
from src.evolution.preference_2d import Preference2DController
from src.utils.pareto import dominates_mixed


A, B, C, D = [0.9, 0.10], [0.5, 0.20], [0.9, 0.20], [0.5, 0.05]


def test_dominance_2d_core():
    assert dominates_mixed(A, B)
    assert dominates_mixed(A, C)
    assert not dominates_mixed(A, D)
    assert not dominates_mixed(D, A)


def test_cost_down_is_positive_improvement():
    imp = objective_improvement([0.5, 0.20], [0.5, 0.10], spec=SPEC_2)
    assert imp > 0


def test_cost_up_is_negative_improvement():
    imp = objective_improvement([0.5, 0.10], [0.5, 0.20], spec=SPEC_2)
    assert imp < 0


def test_tradeoff_not_unconditional_dominate():
    p, c = [0.5, 0.10], [0.8, 0.20]
    assert not dominates_mixed(c, p)
    assert not dominates_mixed(p, c)


def test_peem_credit_chain_2d():
    parent, child = [0.5, 0.20], [0.5, 0.10]
    credit = compute_credit(parent, child, spec=SPEC_2, survived=True)
    assert credit.improvement > 0
    assert credit.mutation_value != 0.0


def test_pareto_estimator_2d_cost_direction():
    est = ParetoContributionEstimator()
    # child dominates many: top score
    pop = [[0.2, 0.8], [0.1, 0.9], [0.3, 0.7]]
    s = est.score_one(parent := [0.5, 0.5], [0.9, 0.1], pop, spec=SPEC_2)
    assert s == 1.0


def test_ppec_selection_fails_if_no_difference():
    """PPEC niching must change which non-dominated points survive truncation."""
    def mk(fit, i):
        return Individual(genome=AgentGenome.random(random.Random(i)), fitness_vector=fit, generation=0)

    # 5 mutually non-dominated trade-offs; select 2 via niching
    pool = [
        mk([0.95, 0.70], 1),  # most success, most cost
        mk([0.80, 0.50], 2),
        mk([0.65, 0.30], 3),
        mk([0.50, 0.15], 4),
        mk([0.35, 0.05], 5),  # least cost
    ]

    def pick_set(pref: str):
        ctrl = Preference2DController(pref)
        nsga = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
        nsga.directions = ctrl.directions
        sel = nsga.select(list(pool), 2)
        return frozenset(id(x) for x in sel)

    s_set = pick_set("success_first")
    c_set = pick_set("cost_first")
    assert s_set != c_set, (
        "PPEC niching must produce different survivor sets under conflict front"
    )
    assert len(s_set) == 2 and len(c_set) == 2


def test_ppec_dominance_not_overridden_by_score():
    # dominated point cannot be selected over its dominator
    dom = Individual(genome=AgentGenome.random(random.Random(9)), fitness_vector=[0.9, 0.1], generation=0)
    dominated = Individual(genome=AgentGenome.random(random.Random(8)), fitness_vector=[0.5, 0.2], generation=0)
    ctrl = Preference2DController("cost_first")
    nsga = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    nsga.directions = ctrl.directions
    sel = nsga.select([dominated, dom], 1)
    assert sel[0] is dom


def test_strength_zero_matches_uniform():
    pool = [Individual(genome=AgentGenome.random(random.Random(i)), fitness_vector=f, generation=0)
            for i, f in enumerate(([0.9, 0.2], [0.5, 0.05], [0.7, 0.3]))]
    ctrl = Preference2DController("success_first", strength=0.0)
    n0 = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    n0.directions = ctrl.directions
    uni = NSGA3(n_objectives=2, divisions=4, seed=0, maximize=(True, False))
    a = {id(x) for x in n0.select(list(pool), 2)}
    b = {id(x) for x in uni.select(list(pool), 2)}
    assert a == b


def test_ppec_loop_selector_not_overwritten():
    def ev(g):
        return [0.6, 0.2]

    from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop

    cfg = MemoryEvolutionConfig(pop_size=4, n_offspring=4, seed=1, n_objectives=2,
                                use_adaptive=False, preference="cost_first")
    loop = MemoryEvolutionLoop(evaluator=ev, config=cfg)
    sel = loop.nsga3
    loop.initialize()
    loop.next_generation()
    assert loop.nsga3 is sel
