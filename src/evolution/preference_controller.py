"""Preference-aware Pareto Evolution Controller (PPEC) — Phase 3.

Manages preference → reference region → selection policy, and scores
solutions for preference satisfaction. Integrates with PEEM mutation control.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.individual import Individual
from src.evolution.preference import (
    PreferenceVector,
    encode_preference,
    preference_satisfaction,
)
from src.evolution.reference_adapter import (
    PreferenceAwareNSGA3,
    adapt_reference_directions,
    reference_region_scores,
)


@dataclass
class PreferenceController:
    """Top-level PPEC interface.

    controller.set_preference({"mode": "accuracy_first"})
    region = controller.get_reference_region()
    score = controller.score_solution(objectives)
    """

    preference: PreferenceVector = field(default_factory=PreferenceVector)
    n_objectives: int = 5
    divisions: int = 3
    strength: float = 1.0
    seed: Optional[int] = 42

    def __post_init__(self) -> None:
        self.selector = PreferenceAwareNSGA3(
            n_objectives=self.n_objectives,
            divisions=self.divisions,
            seed=self.seed,
            preference=self.preference,
            strength=self.strength,
        )

    # ------------------------------------------------------------------ #
    def set_preference(self, spec: Any, *, strength: Optional[float] = None) -> PreferenceVector:
        self.preference = encode_preference(spec)
        self.selector.apply_preference(self.preference, strength=strength)
        return self.preference

    def get_preference(self) -> PreferenceVector:
        return self.preference

    def get_reference_region(self) -> Dict[str, Any]:
        """Weighted reference directions + per-direction preference scores."""
        dirs = self.selector.reference_directions()
        return {
            "preference": self.preference.as_dict(),
            "strength": self.strength,
            "n_directions": len(dirs),
            "directions": dirs,
            "region_scores": reference_region_scores(dirs, self.preference),
        }

    def score_solution(self, objectives: Sequence[float]) -> float:
        return preference_satisfaction(objectives, self.preference)

    def score_individual(self, ind: Individual) -> float:
        if not ind.has_fitness():
            raise ValueError("individual has no fitness_vector")
        return self.score_solution(ind.fitness_vector or [])

    def rank_population(self, individuals: Sequence[Individual]) -> List[Tuple[Individual, float]]:
        scored = [(ind, self.score_individual(ind)) for ind in individuals if ind.has_fitness()]
        return sorted(scored, key=lambda x: -x[1])

    def preferred_region_mask(
        self,
        individuals: Sequence[Individual],
        *,
        quantile: float = 0.5,
    ) -> List[bool]:
        """Mark individuals whose preference score is in the top (1-quantile)."""
        scores = [self.score_individual(i) for i in individuals if i.has_fitness()]
        if not scores:
            return [False] * len(individuals)
        thresh = sorted(scores, reverse=True)[max(0, min(len(scores) - 1, int(len(scores) * (1 - quantile))))]
        out = []
        for ind in individuals:
            if not ind.has_fitness():
                out.append(False)
            else:
                out.append(self.score_individual(ind) >= thresh)
        return out

    # ------------------------------------------------------------------ #
    def select(self, population: List[Individual], pop_size: int) -> List[Individual]:
        """Preference-guided NSGA-III environmental selection."""
        return self.selector.select(population, pop_size)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "preference": self.preference.as_dict(),
            "n_objectives": self.n_objectives,
            "divisions": self.divisions,
            "strength": self.strength,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreferenceController":
        return cls(
            preference=encode_preference(data.get("preference", "balanced")),
            n_objectives=int(data.get("n_objectives", 5)),
            divisions=int(data.get("divisions", 3)),
            strength=float(data.get("strength", 1.0)),
            seed=data.get("seed", 42),
        )


# Preset controllers for common task modes.
def controller_for_mode(mode: str, **kwargs: Any) -> PreferenceController:
    return PreferenceController(preference=encode_preference(mode), **kwargs)
