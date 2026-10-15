"""Objective specification (Phase5-R3-R5-R1) — explicit names + directions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

VERSION_5 = "legacy_5obj"
VERSION_2 = "candidate_2obj"


@dataclass(frozen=True)
class ObjectiveSpec:
    version: str
    names: Tuple[str, ...]
    maximize: Tuple[bool, ...]

    @property
    def n(self) -> int:
        return len(self.names)

    def cost_index(self) -> int:
        for i, n in enumerate(self.names):
            if n == "cost":
                return i
        raise ValueError("no cost objective in spec")

    def to_minimization(self, values: Sequence[float]) -> List[float]:
        if len(values) != self.n:
            raise ValueError(f"dim mismatch: {len(values)} != {self.n}")
        return [-float(v) if m else float(v) for v, m in zip(values, self.maximize)]

    def improvement(self, parent: Sequence[float], child: Sequence[float]) -> float:
        """Positive if child is better under this spec (maximize-aware)."""
        if len(parent) != self.n or len(child) != self.n:
            raise ValueError("dim mismatch")
        gains = []
        for i, (p, c) in enumerate(zip(parent, child)):
            gains.append((float(c) - float(p)) if self.maximize[i] else (float(p) - float(c)))
        pos = sum(max(0.0, g) for g in gains)
        neg = sum(max(0.0, -g) for g in gains)
        return (pos - 0.5 * neg) / self.n

    def dominates(self, a: Sequence[float], b: Sequence[float]) -> bool:
        better = False
        for i, (x, y) in enumerate(zip(a, b)):
            if self.maximize[i]:
                if x < y:
                    return False
                if x > y:
                    better = True
            else:
                if x > y:
                    return False
                if x < y:
                    better = True
        return better

    def validate_vector(self, values: Sequence[float]) -> None:
        if len(values) != self.n:
            raise ValueError(
                f"objective dim {len(values)} != spec {self.n} ({self.version})"
            )


SPEC_5 = ObjectiveSpec(
    version=VERSION_5,
    names=("performance", "efficiency", "cost", "robustness", "autonomy"),
    maximize=(True, True, False, True, True),
)

SPEC_2 = ObjectiveSpec(
    version=VERSION_2,
    names=("performance", "cost"),
    maximize=(True, False),
)


def get_spec(version: str) -> ObjectiveSpec:
    if version == VERSION_5:
        return SPEC_5
    if version == VERSION_2:
        return SPEC_2
    raise ValueError(f"unknown objective version {version!r}")


def assert_same_spec(a: ObjectiveSpec, b: ObjectiveSpec) -> None:
    if a.version != b.version or a.maximize != b.maximize:
        raise ValueError(f"objective spec mismatch: {a.version} vs {b.version}")
