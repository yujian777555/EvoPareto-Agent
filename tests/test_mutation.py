"""Mutation operator correctness tests."""

import random

import pytest

from src.agent.genome import (
    MAX_BUDGET,
    MEMORY_STRATEGIES,
    MIN_BUDGET,
    PLANNER_STRATEGIES,
    REFLECTION_STRATEGIES,
    TOOL_POLICIES,
    AgentGenome,
)
from src.evolution.operators import (
    budget_mutation,
    crossover,
    evolve_individual,
    memory_mutation,
    mutate_genome,
    prompt_mutation,
    reflection_mutation,
    tool_mutation,
)


def make_genome(**kwargs) -> AgentGenome:
    base = dict(
        planner_strategy="cot",
        memory_strategy="episodic",
        reflection_strategy="self_critique",
        tool_policy="balanced",
        reasoning_budget=32,
    )
    base.update(kwargs)
    return AgentGenome(**base)


def test_prompt_mutation_changes_planner():
    rng = random.Random(0)
    g = make_genome()
    for _ in range(20):
        g2 = prompt_mutation(g, rng, rate=1.0)
        assert g2.planner_strategy in PLANNER_STRATEGIES
        assert g2.planner_strategy != g.planner_strategy
        # Other fields unchanged.
        assert g2.memory_strategy == g.memory_strategy
        assert g2.reflection_strategy == g.reflection_strategy
        assert g2.tool_policy == g.tool_policy
        assert g2.reasoning_budget == g.reasoning_budget


def test_memory_mutation_changes_memory():
    rng = random.Random(1)
    g = make_genome()
    g2 = memory_mutation(g, rng, rate=1.0)
    assert g2.memory_strategy in MEMORY_STRATEGIES
    assert g2.memory_strategy != g.memory_strategy
    assert g2.planner_strategy == g.planner_strategy


def test_reflection_mutation_changes_reflection():
    rng = random.Random(2)
    g = make_genome()
    g2 = reflection_mutation(g, rng, rate=1.0)
    assert g2.reflection_strategy in REFLECTION_STRATEGIES
    assert g2.reflection_strategy != g.reflection_strategy


def test_tool_mutation_changes_tool_policy():
    rng = random.Random(3)
    g = make_genome()
    g2 = tool_mutation(g, rng, rate=1.0)
    assert g2.tool_policy in TOOL_POLICIES
    assert g2.tool_policy != g.tool_policy


def test_budget_mutation_within_bounds_and_snapped():
    rng = random.Random(4)
    for budget in (MIN_BUDGET, 32, MAX_BUDGET):
        g = make_genome(reasoning_budget=budget)
        for _ in range(30):
            g2 = budget_mutation(g, rng, rate=1.0, max_step=16)
            assert MIN_BUDGET <= g2.reasoning_budget <= MAX_BUDGET
            assert g2.reasoning_budget % 8 == 0
            assert g2.reasoning_budget != g.reasoning_budget


def test_mutation_rate_zero_is_identity():
    rng = random.Random(5)
    g = make_genome()
    g2 = mutate_genome(g, rng, n_mutations=5, rate=0.0)
    # rate is passed to each mutator; rate=0 means no mutation.
    assert g2 == g


def test_mutate_genome_valid_output():
    rng = random.Random(6)
    g = make_genome()
    g2 = mutate_genome(g, rng, n_mutations=3, rate=1.0)
    assert isinstance(g2, AgentGenome)  # validates fields


def test_crossover_preserves_validity():
    rng = random.Random(7)
    a = make_genome()
    b = make_genome(
        planner_strategy="tree_search",
        memory_strategy="hybrid",
        reflection_strategy="iterative",
        tool_policy="no_tools",
        reasoning_budget=120,
    )
    c1, c2 = crossover(a, b, rng, rate=1.0)
    assert isinstance(c1, AgentGenome) and isinstance(c2, AgentGenome)
    # Field-wise children of parents.
    for child in (c1, c2):
        assert child.planner_strategy in (a.planner_strategy, b.planner_strategy)
        assert child.memory_strategy in (a.memory_strategy, b.memory_strategy)


def test_evolve_individual_sets_generation():
    from src.agent.individual import Individual

    rng = random.Random(8)
    parent = Individual(genome=make_genome(), generation=0)
    child = evolve_individual(parent, rng, generation=5, mutation_rate=1.0)
    assert child.generation == 5
    assert child.genome is not parent.genome
    assert child.individual_id != parent.individual_id
