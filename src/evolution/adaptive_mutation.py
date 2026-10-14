"""Adaptive mutation controller + operator registry (Phase 2).

Replaces uniform random mutation with a probability distribution derived
from MutationExperience. Existing Phase 0 operators are preserved.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evolution.experience import MutationExperience
from src.evolution.operators import (
    budget_mutation,
    memory_mutation,
    prompt_mutation,
    reflection_mutation,
    tool_mutation,
)


MutationFn = Callable[..., AgentGenome]


@dataclass
class MutationOperator:
    name: str
    fn: MutationFn


class MutationOperatorRegistry:
    """Extensible registry of agent-specific mutation operators."""

    def __init__(self) -> None:
        self._ops: Dict[str, MutationOperator] = {}

    def register(self, name: str, fn: MutationFn) -> None:
        if not name:
            raise ValueError("mutation name must be non-empty")
        self._ops[name] = MutationOperator(name=name, fn=fn)

    def get(self, name: str) -> MutationOperator:
        if name not in self._ops:
            raise KeyError(f"unknown mutation operator: {name!r}")
        return self._ops[name]

    def names(self) -> List[str]:
        return sorted(self._ops)

    def sample(self, rng: random.Random, probabilities: Mapping[str, float]) -> MutationOperator:
        names = self.names()
        if not names:
            raise RuntimeError("mutation registry is empty")
        weights = [max(0.0, float(probabilities.get(n, 0.0))) for n in names]
        if sum(weights) <= 0:
            return self.get(rng.choice(names))
        return self.get(rng.choices(names, weights=weights, k=1)[0])

    def apply(
        self,
        name: str,
        genome: AgentGenome,
        rng: random.Random,
        *,
        rate: float = 1.0,
    ) -> AgentGenome:
        return self.get(name).fn(genome, rng, rate=rate)


def default_registry() -> MutationOperatorRegistry:
    reg = MutationOperatorRegistry()
    reg.register("planner", prompt_mutation)
    reg.register("memory", memory_mutation)
    reg.register("reflection", reflection_mutation)
    reg.register("tool", tool_mutation)
    reg.register("budget", budget_mutation)
    return reg


@dataclass
class AdaptiveMutationController:
    """Maps MutationExperience -> mutation probability distribution.

    After enough evidence, probabilities concentrate on historically
    effective mutation types (e.g. planner 0.45, budget 0.10).
    """

    experience: MutationExperience
    registry: MutationOperatorRegistry = field(default_factory=default_registry)
    epsilon: float = 0.08  # explore: flatten distribution
    min_prob: float = 0.02

    def probability_distribution(self) -> Dict[str, float]:
        names = self.registry.names()
        if not names:
            return {}
        scores = {n: max(1e-9, self.experience.get_score(n)) for n in names}
        total = sum(scores.values())
        probs = {n: scores[n] / total for n in names}
        # Mix with uniform for exploration.
        uniform = 1.0 / len(names)
        mixed = {
            n: (1.0 - self.epsilon) * probs[n] + self.epsilon * uniform for n in names
        }
        # Enforce a small floor then renormalize.
        floored = {n: max(self.min_prob, mixed[n]) for n in names}
        s = sum(floored.values())
        return {n: floored[n] / s for n in names}

    def select_mutation(self, rng: random.Random) -> str:
        dist = self.probability_distribution()
        names = list(dist.keys())
        weights = [dist[n] for n in names]
        return rng.choices(names, weights=weights, k=1)[0]

    def mutate(
        self,
        genome: AgentGenome,
        rng: random.Random,
        *,
        n_mutations: int = 1,
        rate: float = 1.0,
    ) -> Tuple[AgentGenome, List[str]]:
        """Apply `n_mutations` adaptively chosen mutations. Returns (genome, names)."""
        if n_mutations < 1:
            raise ValueError("n_mutations must be >= 1")
        current = genome
        used: List[str] = []
        for _ in range(n_mutations):
            name = self.select_mutation(rng)
            current = self.registry.apply(name, current, rng, rate=rate)
            used.append(name)
        return current, used

    def mutate_individual(
        self,
        parent: Individual,
        rng: random.Random,
        *,
        generation: int,
        n_mutations: int = 1,
        rate: float = 1.0,
    ) -> Tuple[Individual, List[str]]:
        child_genome, used = self.mutate(
            parent.genome, rng, n_mutations=n_mutations, rate=rate
        )
        child = Individual(
            genome=child_genome,
            fitness_vector=None,
            generation=generation,
            metadata={
                "parent_id": parent.individual_id,
                "mutation_types": used,
                "operator": "adaptive_mutation",
            },
        )
        return child, used
