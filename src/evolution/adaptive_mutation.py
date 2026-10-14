"""Adaptive mutation controller + operator registry (Phase 2 / 2.5).

Phase 2: probability from success-rate MutationExperience.
Phase 2.5: probability from Pareto-aware Mutation Value (PEEM) when provided.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple

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


class ScoreSource(Protocol):
    """Anything that can score a mutation type (Experience or PEEM)."""

    def get_score(self, mutation_type: str) -> float: ...


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
    """Maps mutation utility -> probability distribution.

    Phase 2.5-R1: temperature-softmax selection
        p_i = exp(score_i / T) / sum_j exp(score_j / T)
    with optional linear annealing T: T0 → T_min over `total_steps`.
    """

    experience: ScoreSource
    registry: MutationOperatorRegistry = field(default_factory=default_registry)
    epsilon: float = 0.08  # explore: flatten distribution
    min_prob: float = 0.02
    # Phase 2.5: if True, treat low MV as more strongly suppressed.
    sharpness: float = 1.0
    # Phase 2.5-R1 temperature annealing
    temperature: float = 1.0
    temperature_min: float = 0.2
    temperature_step: float = 0.0  # linear decay per select_mutation call
    use_softmax: bool = True
    _steps: int = 0

    def current_temperature(self) -> float:
        if self.temperature_step <= 0:
            return self.temperature
        t = self.temperature - self.temperature_step * self._steps
        return max(self.temperature_min, t)

    def _softmax(self, scores: Sequence[float]) -> List[float]:
        t = max(1e-6, self.current_temperature())
        xs = [float(s) / t for s in scores]
        m = max(xs)
        exps = [math.exp(x - m) for x in xs]
        s = sum(exps)
        return [e / s for e in exps]

    def probability_distribution(self) -> Dict[str, float]:
        names = self.registry.names()
        if not names:
            return {}
        raw = [max(1e-9, float(self.experience.get_score(n))) for n in names]
        min_raw = min(raw)
        if min_raw <= 0:
            raw = [r - min_raw + 1e-3 for r in raw]
        if self.sharpness != 1.0:
            raw = [r ** self.sharpness for r in raw]

        if self.use_softmax:
            probs_list = self._softmax(raw)
        else:
            total = sum(raw)
            probs_list = [r / total for r in raw]

        probs = {n: probs_list[i] for i, n in enumerate(names)}
        uniform = 1.0 / len(names)
        mixed = {n: (1.0 - self.epsilon) * probs[n] + self.epsilon * uniform for n in names}
        floored = {n: max(self.min_prob, mixed[n]) for n in names}
        s = sum(floored.values())
        return {n: floored[n] / s for n in names}

    def select_mutation(self, rng: random.Random) -> str:
        self._steps += 1
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
