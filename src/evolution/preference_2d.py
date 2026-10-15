"""Two-objective PPEC (Phase5-R3-R5-R1 Task D)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.evaluation.objective_spec import SPEC_2, ObjectiveSpec
from src.evolution.nsga3 import generate_reference_directions
from src.evolution.reference_adapter import adapt_reference_directions

# Frozen candidate weights (Planner to confirm).
PREF_2D: Dict[str, Tuple[float, float]] = {
    # (success_weight, cost_weight) — cost weight means "care about low cost"
    "success_first": (0.8, 0.2),
    "cost_first": (0.25, 0.75),
    "balanced": (0.5, 0.5),
}


@dataclass
class Preference2D:
    name: str
    success_w: float
    cost_w: float

    def as_tuple(self) -> Tuple[float, float]:
        return (float(self.success_w), float(self.cost_w))


def encode_preference_2d(spec: Any) -> Preference2D:
    if isinstance(spec, Preference2D):
        return spec
    if isinstance(spec, str):
        if spec not in PREF_2D:
            raise ValueError(f"unknown 2d preference {spec!r}")
        a, b = PREF_2D[spec]
        return Preference2D(spec, a, b)
    if isinstance(spec, dict):
        if "name" in spec:
            return encode_preference_2d(str(spec["name"]))
        return Preference2D("custom", float(spec["success_w"]), float(spec["cost_w"]))
    raise TypeError(f"cannot encode 2d preference from {type(spec)}")


def preference_satisfaction_2d(
    performance: float,
    cost: float,
    pref: Preference2D,
) -> float:
    """Higher better. cost already lower-is-better → use 1-cost."""
    s = max(0.0, min(1.0, float(performance)))
    c = max(0.0, min(1.0, float(cost)))
    achieve = (s, 1.0 - c)
    w = pref.as_tuple()
    wsum = w[0] + w[1]
    if wsum <= 1e-12:
        return 0.5 * (achieve[0] + achieve[1])
    return (w[0] * achieve[0] + w[1] * achieve[1]) / wsum


class Preference2DController:
    def __init__(self, preference: Any = "balanced", *, divisions: int = 4, strength: float = 1.0) -> None:
        self.preference = encode_preference_2d(preference)
        self.strength = float(strength)
        self.divisions = divisions
        self._base = generate_reference_directions(2, divisions)
        self.directions = self._adapt()

    def _adapt(self) -> List[List[float]]:
        # Map 2D preference onto 2D "preference vector" for adapt_reference_directions.
        w = self.preference.as_tuple()
        s = w[0] + w[1]
        pref_vec = tuple(x / s for x in w) if s > 0 else (0.5, 0.5)

        class _P:
            def normalized(self_inner):
                return self_inner

            def as_tuple(self_inner):
                return pref_vec

            def unit(self_inner):
                n = sum(x * x for x in pref_vec) ** 0.5 or 1.0
                return tuple(x / n for x in pref_vec)

        return adapt_reference_directions(self._base, _P(), strength=self.strength)  # type: ignore

    def score(self, performance: float, cost: float) -> float:
        return preference_satisfaction_2d(performance, cost, self.preference)

    def select(self, rows: Sequence[Sequence[float]]) -> int:
        """Argmax preference satisfaction among [perf, cost] rows."""
        best_i, best_s = 0, -1.0
        for i, r in enumerate(rows):
            if len(r) != 2:
                raise ValueError(f"need exactly 2 objectives, got {len(r)}")
            s = self.score(float(r[0]), float(r[1]))
            if s > best_s:
                best_i, best_s = i, s
        return best_i

    def region_summary(self) -> Dict[str, Any]:
        return {
            "preference": self.preference.name,
            "weights": self.preference.as_tuple(),
            "n_directions": len(self.directions),
            "directions_differ_from_uniform": self.directions != self._base,
        }
