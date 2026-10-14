"""Preference-guided NSGA-III reference direction adaptation (Phase 3).

Does **not** modify `src/evolution/nsga3.py`. We subclass `NSGA3` and reshape
its reference directions toward the preference region of the simplex.

Adaptation (preference-guided association):
    w'_i = w_i * (ε + p_i) , then L1 renormalize
where p is the L1-normalized preference. Directions aligned with important
objectives keep more mass; extreme directions on low-weight axes shrink.

Also provides a scoring helper for preferred-region membership.
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from src.agent.individual import Individual
from src.evolution.nsga3 import NSGA3, generate_reference_directions
from src.evolution.preference import PreferenceVector, preference_satisfaction


def adapt_reference_directions(
    directions: Sequence[Sequence[float]],
    preference: PreferenceVector,
    *,
    strength: float = 1.0,
    eps: float = 0.15,
) -> List[List[float]]:
    """Bias reference directions toward `preference`.

    strength=0 returns the original directions (up to renormalization).
    strength=1 is the full preference-guided adaptation.
    """
    if not directions:
        return []
    pref = preference.normalized().as_tuple()
    s = min(1.0, max(0.0, float(strength)))
    out: List[List[float]] = []
    for w in directions:
        if len(w) != len(pref):
            raise ValueError("direction / preference dimension mismatch")
        mixed = []
        for wi, pi in zip(w, pref):
            factor = (1.0 - s) * 1.0 + s * (eps + pi)
            mixed.append(max(0.0, float(wi) * factor))
        total = sum(mixed)
        if total <= 1e-12:
            out.append([1.0 / len(mixed)] * len(mixed))
        else:
            out.append([x / total for x in mixed])
    return out


def reference_region_scores(
    directions: Sequence[Sequence[float]],
    preference: PreferenceVector,
) -> List[float]:
    """Similarity of each direction to the preference unit vector."""
    pu = preference.unit()
    scores = []
    for w in directions:
        wu = _l2(w)
        scores.append(max(0.0, min(1.0, sum(a * b for a, b in zip(wu, pu)))))
    return scores


def _l2(vec: Sequence[float]) -> Tuple[float, ...]:
    n = math.sqrt(sum(float(x) * float(x) for x in vec))
    if n <= 1e-12:
        return tuple(0.0 for _ in vec)
    return tuple(float(x) / n for x in vec)


def weighted_pareto_score(
    objectives: Sequence[float],
    preference: PreferenceVector,
) -> float:
    """Scalar preference-weighted score (higher = more preferred)."""
    return preference_satisfaction(objectives, preference)


class PreferenceAwareNSGA3(NSGA3):
    """NSGA-III with preference-adapted reference directions.

    Selection API is identical to `NSGA3.select`; only the internal
    reference direction set is reshaped.
    """

    def __init__(
        self,
        n_objectives: int = 5,
        divisions: int = 3,
        seed: Optional[int] = 42,
        maximize: Optional[Sequence[bool]] = None,
        preference: Optional[PreferenceVector] = None,
        strength: float = 1.0,
    ) -> None:
        super().__init__(
            n_objectives=n_objectives,
            divisions=divisions,
            seed=seed,
            maximize=maximize,
        )
        self.preference = preference or PreferenceVector()
        self.strength = float(strength)
        self._base_directions = [list(d) for d in self.directions]
        self.apply_preference(self.preference, strength=self.strength)

    def apply_preference(self, preference: PreferenceVector, *, strength: Optional[float] = None) -> None:
        self.preference = preference
        if strength is not None:
            self.strength = float(strength)
        self.directions = adapt_reference_directions(
            self._base_directions,
            preference,
            strength=self.strength,
        )

    def base_directions(self) -> List[List[float]]:
        return [list(d) for d in self._base_directions]
