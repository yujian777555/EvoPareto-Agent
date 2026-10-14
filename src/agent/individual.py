"""Evolutionary individual wrapping an AgentGenome + fitness metadata."""

from __future__ import annotations

import copy
import itertools
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from src.agent.genome import AgentGenome


_ID_COUNTER = itertools.count(1)


def _next_id() -> int:
    return next(_ID_COUNTER)


@dataclass
class Individual:
    """One candidate agent configuration in the evolutionary population.

    fitness_vector
        Raw objective values, conventionally ordered as
        [performance, efficiency, cost, robustness, autonomy].
        Higher is better for performance/efficiency/robustness/autonomy;
        lower is better for cost. Dominance handling is done in NSGA-III.
    """

    genome: AgentGenome
    fitness_vector: Optional[List[float]] = None
    generation: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    individual_id: int = field(default_factory=_next_id)

    def __post_init__(self) -> None:
        if self.fitness_vector is not None:
            self.fitness_vector = [float(x) for x in self.fitness_vector]

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "individual_id": self.individual_id,
            "generation": self.generation,
            "genome": self.genome.to_dict(),
            "fitness_vector": (
                None if self.fitness_vector is None else list(self.fitness_vector)
            ),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Individual":
        if "genome" not in data:
            raise ValueError("Individual.from_dict requires 'genome'")
        fitness = data.get("fitness_vector")
        ind = cls(
            genome=AgentGenome.from_dict(data["genome"]),
            fitness_vector=None if fitness is None else [float(x) for x in fitness],
            generation=int(data.get("generation", 0)),
            metadata=copy.deepcopy(dict(data.get("metadata", {}))),
        )
        # Preserve id when present so round-trips stay stable in tests/logs.
        if "individual_id" in data:
            ind.individual_id = int(data["individual_id"])
        return ind

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "Individual":
        return cls.from_dict(json.loads(payload))

    def clone(self, *, reset_id: bool = False) -> "Individual":
        child = Individual(
            genome=self.genome.clone(),
            fitness_vector=(
                None if self.fitness_vector is None else list(self.fitness_vector)
            ),
            generation=self.generation,
            metadata=copy.deepcopy(self.metadata),
        )
        if not reset_id:
            child.individual_id = self.individual_id
        else:
            child.individual_id = _next_id()
        return child

    # ------------------------------------------------------------------ #
    # Fitness helpers
    # ------------------------------------------------------------------ #
    @property
    def n_objectives(self) -> int:
        return 0 if self.fitness_vector is None else len(self.fitness_vector)

    def set_fitness(self, values: Sequence[float]) -> None:
        self.fitness_vector = [float(x) for x in values]

    def has_fitness(self) -> bool:
        return self.fitness_vector is not None

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"Individual(id={self.individual_id}, gen={self.generation}, "
            f"fitness={self.fitness_vector}, genome={self.genome.to_dict()})"
        )
