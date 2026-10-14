"""Preference representation and encoding (Phase 3).

PreferenceVector weights the five paper objectives:
    [performance, efficiency, cost, robustness, autonomy]

Higher weight => that objective matters more in the task profile.
Cost is still *minimized* in the objective space; its preference weight
means "sensitivity to cost" (how much we care about low cost).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from src.evaluation.objectives import OBJECTIVE_NAMES

# Canonical task modes (structured encoder; no NLP in Phase 3).
PREFERENCE_MODES: Dict[str, Tuple[float, float, float, float, float]] = {
    # performance, efficiency, cost, robustness, autonomy
    "accuracy_first": (0.9, 0.3, 0.2, 0.8, 0.5),
    "cost_first": (0.3, 0.7, 0.9, 0.4, 0.4),
    "balanced": (0.5, 0.5, 0.5, 0.5, 0.5),
    "robust_first": (0.5, 0.4, 0.3, 0.9, 0.5),
    "efficiency_first": (0.4, 0.9, 0.6, 0.3, 0.4),
    "autonomy_first": (0.5, 0.3, 0.3, 0.5, 0.9),
    "latency_first": (0.5, 0.9, 0.4, 0.4, 0.3),  # efficiency ~ latency
}


@dataclass(frozen=True)
class PreferenceVector:
    """Serializable, comparable, normalizable task preference."""

    performance: float = 0.5
    efficiency: float = 0.5
    cost: float = 0.5
    robustness: float = 0.5
    autonomy: float = 0.5

    def __post_init__(self) -> None:
        for name in OBJECTIVE_NAMES:
            v = getattr(self, name)
            if not (0.0 <= float(v) <= 1.0):
                raise ValueError(f"{name} must be in [0, 1], got {v}")

    # ------------------------------------------------------------------ #
    def as_tuple(self) -> Tuple[float, float, float, float, float]:
        return (
            float(self.performance),
            float(self.efficiency),
            float(self.cost),
            float(self.robustness),
            float(self.autonomy),
        )

    def as_dict(self) -> Dict[str, float]:
        return dict(zip(OBJECTIVE_NAMES, self.as_tuple()))

    @classmethod
    def from_seq(cls, values: Sequence[float]) -> "PreferenceVector":
        if len(values) != 5:
            raise ValueError("PreferenceVector requires 5 components")
        return cls(*[float(v) for v in values])

    @classmethod
    def from_dict(cls, data: Mapping[str, float]) -> "PreferenceVector":
        return cls.from_seq([float(data[n]) for n in OBJECTIVE_NAMES])

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, payload: str) -> "PreferenceVector":
        return cls.from_dict(json.loads(payload))

    # ------------------------------------------------------------------ #
    def normalized(self) -> "PreferenceVector":
        """L1-normalized weights in [0, 1] that sum to 1 (redistributed)."""
        vals = self.as_tuple()
        s = sum(vals)
        if s <= 1e-12:
            return PreferenceVector(0.2, 0.2, 0.2, 0.2, 0.2)
        scaled = [v / s for v in vals]
        # Rescale to [0,1] range while keeping proportions.
        m = max(scaled) if scaled else 1.0
        if m <= 1e-12:
            return PreferenceVector(0.2, 0.2, 0.2, 0.2, 0.2)
        return PreferenceVector.from_seq([v / m for v in scaled])

    def unit(self) -> Tuple[float, ...]:
        """L2 unit vector (for cosine similarity)."""
        vals = self.as_tuple()
        n = math.sqrt(sum(v * v for v in vals))
        if n <= 1e-12:
            return (0.0,) * 5
        return tuple(v / n for v in vals)

    # ------------------------------------------------------------------ #
    def key(self) -> Tuple[float, ...]:
        return self.as_tuple()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PreferenceVector):
            return NotImplemented
        return self.key() < other.key()

    def similarity(self, other: "PreferenceVector") -> float:
        """Cosine similarity in [0, 1] of unit vectors (non-negative)."""
        a, b = self.unit(), other.unit()
        c = sum(x * y for x, y in zip(a, b))
        return max(0.0, min(1.0, c))

    def distance(self, other: "PreferenceVector") -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(self.as_tuple(), other.as_tuple())))

    def clone(self, **changes: float) -> "PreferenceVector":
        d = self.as_dict()
        d.update(changes)
        return PreferenceVector.from_dict(d)


def encode_preference(spec: Any) -> PreferenceVector:
    """Structured preference encoder (no NLP).

    Accepts:
      - "accuracy_first" / mode name
      - {"mode": "cost_first"}
      - {"performance": 0.8, ...}
      - PreferenceVector
      - [0.9, 0.3, 0.2, 0.8, 0.5]
    """
    if isinstance(spec, PreferenceVector):
        return spec
    if isinstance(spec, str):
        key = spec.strip().lower()
        if key not in PREFERENCE_MODES:
            raise ValueError(f"unknown preference mode: {spec!r}")
        return PreferenceVector.from_seq(PREFERENCE_MODES[key])
    if isinstance(spec, Mapping):
        if "mode" in spec:
            return encode_preference(str(spec["mode"]))
        return PreferenceVector.from_dict(spec)
    if isinstance(spec, (list, tuple)):
        return PreferenceVector.from_seq(spec)
    raise TypeError(f"cannot encode preference from {type(spec).__name__}")


def preference_satisfaction(
    objectives: Sequence[float],
    preference: PreferenceVector,
) -> float:
    """How well a solution matches the preference, in [0, 1].

    For maximize objectives: higher raw is better (weight by preference).
    For cost: lower raw is better (score = 1 - cost).
    """
    if len(objectives) != 5:
        raise ValueError("objectives must have 5 components")
    p = preference.normalized()
    w = p.as_tuple()
    # Achievement in "higher is better" space.
    achieve = []
    for i, v in enumerate(objectives):
        v = float(v)
        if i == 2:  # cost
            achieve.append(1.0 - min(1.0, max(0.0, v)))
        else:
            achieve.append(min(1.0, max(0.0, v)))
    wsum = sum(w)
    if wsum <= 1e-12:
        return sum(achieve) / 5.0
    return float(sum(wi * ai for wi, ai in zip(w, achieve)) / wsum)
