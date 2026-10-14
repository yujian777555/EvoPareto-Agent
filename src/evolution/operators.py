"""Agent-specific mutation / crossover operators for evolutionary search."""

from __future__ import annotations

import random
from typing import Callable, List, Optional, Sequence, Tuple

from src.agent.genome import (
    MAX_BUDGET,
    MEMORY_STRATEGIES,
    MIN_BUDGET,
    PLANNER_STRATEGIES,
    REFLECTION_STRATEGIES,
    TOOL_POLICIES,
    AgentGenome,
)
from src.agent.individual import Individual


MutationFn = Callable[[AgentGenome, random.Random], AgentGenome]


def prompt_mutation(
    genome: AgentGenome, rng: random.Random, *, rate: float = 1.0
) -> AgentGenome:
    """Change the planner strategy (prompt / planning mode)."""
    if rng.random() > rate:
        return genome
    choices = [s for s in PLANNER_STRATEGIES if s != genome.planner_strategy]
    if not choices:
        return genome
    return genome.replace(planner_strategy=rng.choice(choices))


def memory_mutation(
    genome: AgentGenome, rng: random.Random, *, rate: float = 1.0
) -> AgentGenome:
    """Change the memory policy."""
    if rng.random() > rate:
        return genome
    choices = [s for s in MEMORY_STRATEGIES if s != genome.memory_strategy]
    if not choices:
        return genome
    return genome.replace(memory_strategy=rng.choice(choices))


def reflection_mutation(
    genome: AgentGenome, rng: random.Random, *, rate: float = 1.0
) -> AgentGenome:
    """Change the reflection / self-critique policy."""
    if rng.random() > rate:
        return genome
    choices = [s for s in REFLECTION_STRATEGIES if s != genome.reflection_strategy]
    if not choices:
        return genome
    return genome.replace(reflection_strategy=rng.choice(choices))


def tool_mutation(
    genome: AgentGenome, rng: random.Random, *, rate: float = 1.0
) -> AgentGenome:
    """Change the tool usage policy."""
    if rng.random() > rate:
        return genome
    choices = [s for s in TOOL_POLICIES if s != genome.tool_policy]
    if not choices:
        return genome
    return genome.replace(tool_policy=rng.choice(choices))


def budget_mutation(
    genome: AgentGenome,
    rng: random.Random,
    *,
    rate: float = 1.0,
    max_step: int = 16,
) -> AgentGenome:
    """Perturb the reasoning budget within valid bounds."""
    if rng.random() > rate:
        return genome
    step = rng.randint(-max_step, max_step)
    # Snap to multiple of 8 to stay on the discrete budget grid.
    new_budget = int(round((genome.reasoning_budget + step) / 8.0) * 8)
    new_budget = max(MIN_BUDGET, min(MAX_BUDGET, new_budget))
    if new_budget == genome.reasoning_budget:
        # Force a different neighbor if the snap collapsed.
        delta = 8 if new_budget < MAX_BUDGET else -8
        new_budget = max(MIN_BUDGET, min(MAX_BUDGET, new_budget + delta))
    return genome.replace(reasoning_budget=new_budget)


# Registry used by the default multi-operator mutator.
DEFAULT_MUTATORS: Tuple[Tuple[str, MutationFn], ...] = (
    ("prompt", prompt_mutation),
    ("memory", memory_mutation),
    ("reflection", reflection_mutation),
    ("tool", tool_mutation),
    ("budget", budget_mutation),
)


def mutate_genome(
    genome: AgentGenome,
    rng: random.Random,
    *,
    n_mutations: int = 1,
    mutators: Optional[Sequence[MutationFn]] = None,
    rate: float = 1.0,
) -> AgentGenome:
    """Apply `n_mutations` randomly chosen agent-specific mutations."""
    if n_mutations < 1:
        raise ValueError("n_mutations must be >= 1")
    pool: Sequence[MutationFn]
    if mutators is None:
        pool = tuple(fn for _, fn in DEFAULT_MUTATORS)
    else:
        pool = mutators
    if not pool:
        return genome

    current = genome
    for _ in range(n_mutations):
        fn = rng.choice(list(pool))
        current = fn(current, rng, rate=rate)  # type: ignore[call-arg]
    return current


def crossover(
    a: AgentGenome, b: AgentGenome, rng: random.Random, *, rate: float = 0.5
) -> Tuple[AgentGenome, AgentGenome]:
    """Uniform crossover over genome fields."""
    if rng.random() > rate:
        return a.clone(), b.clone()

    a_dict, b_dict = a.to_dict(), b.to_dict()
    child_a, child_b = {}, {}
    for key in a.fields():
        if rng.random() < 0.5:
            child_a[key] = a_dict[key]
            child_b[key] = b_dict[key]
        else:
            child_a[key] = b_dict[key]
            child_b[key] = a_dict[key]
    return AgentGenome.from_dict(child_a), AgentGenome.from_dict(child_b)


def evolve_individual(
    parent: Individual,
    rng: random.Random,
    *,
    generation: int,
    n_mutations: int = 1,
    mutation_rate: float = 0.8,
) -> Individual:
    """Produce a mutated child Individual from a parent."""
    if rng.random() > mutation_rate:
        child = parent.clone(reset_id=True)
    else:
        child_genome = mutate_genome(parent.genome, rng, n_mutations=n_mutations)
        child = Individual(
            genome=child_genome,
            fitness_vector=None,
            generation=generation,
            metadata={"parent_id": parent.individual_id, "operator": "mutation"},
        )
    child.generation = generation
    return child
