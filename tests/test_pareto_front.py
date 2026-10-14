"""Pareto-front correctness tests (paper semantics: max except cost)."""

import random

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.evaluator import ToyEvaluator
from src.evaluation.objectives import OBJECTIVE_NAMES, to_maximization, to_minimization
from src.evolution.population import Population, PopulationConfig
from src.utils.pareto import (
    dominates_max,
    dominates_mixed,
    filter_pareto_max,
    filter_pareto_mixed,
    pareto_mask_max,
    pareto_mask_mixed,
    hypervolume_2d_max,
)


def test_objective_names_length():
    assert len(OBJECTIVE_NAMES) == 5
    assert OBJECTIVE_NAMES[0] == "performance"
    assert OBJECTIVE_NAMES[2] == "cost"


def test_to_minimization_signs():
    raw = [0.7, 0.6, 0.2, 0.8, 0.9]  # cost is minimize
    mini = to_minimization(raw)
    assert mini[0] == -0.7
    assert mini[1] == -0.6
    assert mini[2] == 0.2
    assert mini[3] == -0.8
    assert mini[4] == -0.9
    assert to_maximization(mini) == raw


def test_pareto_mask_simple():
    rows = [
        [1.0, 1.0],
        [2.0, 0.5],
        [0.5, 2.0],
        [0.2, 0.2],
    ]
    mask = pareto_mask_max(rows)
    assert mask == [True, True, True, False]
    front = filter_pareto_max(rows)
    assert len(front) == 3


def test_dominates_mixed_respects_cost_direction():
    # A better on performance AND cost; other objectives equal -> A dominates B.
    a = [0.9, 0.5, 0.2, 0.5, 0.5]
    b = [0.5, 0.5, 0.5, 0.5, 0.5]
    assert dominates_mixed(a, b)
    assert not dominates_mixed(b, a)
    # Wrong all-max interpretation would disagree on cost.
    assert not dominates_max(a, b)


def test_nsga3_prefers_higher_performance_same_else():
    """Regression: selection must use max/min signs, not raw minimization."""
    from src.evolution.nsga3 import NSGA3

    a = Individual(
        genome=AgentGenome.random(random.Random(1)),
        fitness_vector=[0.9, 0.5, 0.2, 0.5, 0.5],
        generation=0,
    )
    b = Individual(
        genome=AgentGenome.random(random.Random(2)),
        fitness_vector=[0.5, 0.5, 0.5, 0.5, 0.5],
        generation=0,
    )
    nsga = NSGA3(n_objectives=5, divisions=2, seed=0)
    chosen = nsga.select([a, b], pop_size=1)
    assert len(chosen) == 1
    assert chosen[0].fitness_vector[0] == 0.9
    front = nsga.pareto_front([a, b])
    assert len(front) == 1
    assert front[0].fitness_vector[0] == 0.9


def test_evaluator_deterministic_and_bounds():
    ev = ToyEvaluator(noise_scale=1.0)
    g = AgentGenome.random(random.Random(0))
    v1 = ev.evaluate(g)
    v2 = ev.evaluate(g)
    assert v1 == v2
    assert len(v1) == 5
    assert all(0.0 <= x <= 1.0 for x in v1)


def test_evaluator_tradeoffs_exist():
    """A cheap config and an expensive config should not dominate each other."""
    ev = ToyEvaluator(noise_scale=0.0)
    cheap = AgentGenome(
        planner_strategy="direct",
        memory_strategy="none",
        reflection_strategy="none",
        tool_policy="no_tools",
        reasoning_budget=8,
    )
    strong = AgentGenome(
        planner_strategy="tree_search",
        memory_strategy="hybrid",
        reflection_strategy="iterative",
        tool_policy="tool_first",
        reasoning_budget=128,
    )
    c = ev.evaluate(cheap)
    s = ev.evaluate(strong)
    # strong should have higher performance, cheap should have lower cost
    assert s[0] > c[0]
    assert c[2] < s[2]
    # Neither dominates the other under paper max/min semantics.
    assert not dominates_mixed(c, s)
    assert not dominates_mixed(s, c)


def test_population_front_matches_manual_pareto():
    ev = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=20, n_offspring=20, seed=7)
    pop = Population(evaluator=ev.evaluate, config=cfg)
    pop.initialize()
    pop.run(3)

    all_rows = [list(ind.fitness_vector) for ind in pop.individuals]
    manual = filter_pareto_mixed(all_rows)
    algo_front = pop.pareto_front()
    algo_rows = [list(ind.fitness_vector) for ind in algo_front]

    # Every algorithm-front point must be non-dominated among the full population.
    mask = pareto_mask_mixed(all_rows)
    for row in algo_rows:
        # find at least one matching population member that is non-dominated
        assert any(
            mask[i] and all_rows[i] == row for i in range(len(all_rows))
        ), f"front row {row} not in manual non-dominated set"

    # Counts should match (as sets of tuples).
    assert len(algo_rows) == len(manual)


def test_hypervolume_2d_sanity():
    front = [[0.8, 0.8], [0.9, 0.5]]
    hv = hypervolume_2d_max(front, ref=[0.0, 0.0])
    assert hv > 0
    # Dominating point should increase HV.
    hv2 = hypervolume_2d_max(front + [[1.0, 1.0]], ref=[0.0, 0.0])
    assert hv2 > hv
