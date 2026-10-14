"""Per-generation credit normalization (Phase 2.5-R1).

z = (x - mean) / std

Applied to improvement / pareto contribution / diversity / survival so the
composite mutation value mixes comparable signals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


def mean_std(values: Sequence[float]) -> Tuple[float, float]:
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return 0.0, 1.0
    mu = sum(vals) / n
    var = sum((v - mu) ** 2 for v in vals) / n
    std = math.sqrt(var)
    return mu, (std if std > 1e-12 else 1.0)


def zscore(values: Sequence[float], *, mu: Optional[float] = None, std: Optional[float] = None) -> List[float]:
    """z-score with optional precomputed mean/std; degenerate std → zeros."""
    vals = [float(v) for v in values]
    if not vals:
        return []
    if mu is None or std is None:
        mu, std = mean_std(vals)
    if std <= 1e-12:
        return [0.0] * len(vals)
    return [(v - mu) / std for v in vals]


def zscore_clip(values: Sequence[float], clip: float = 3.0) -> List[float]:
    return [max(-clip, min(clip, z)) for z in zscore(values)]


@dataclass
class GenerationNormalizer:
    """Collects a batch of raw component scores and returns z-normalized ones.

    Typical use per generation:
        norm = GenerationNormalizer()
        for each child: norm.add("improvement", x); ...
        norm.fit()
        for each child: norm.transform_row({...})
    """

    clip: float = 3.0
    _store: Dict[str, List[float]] = None  # type: ignore[assignment]
    _stats: Dict[str, Tuple[float, float]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self._store = {}
        self._stats = {}

    def add(self, name: str, value: float) -> None:
        self._store.setdefault(name, []).append(float(value))

    def add_row(self, row: Mapping[str, float]) -> None:
        for k, v in row.items():
            self.add(k, v)

    def fit(self) -> "GenerationNormalizer":
        self._stats = {k: mean_std(v) for k, v in self._store.items()}
        return self

    def transform(self, name: str, value: float) -> float:
        mu, std = self._stats.get(name, (0.0, 1.0))
        if std <= 1e-12:
            return 0.0
        z = (float(value) - mu) / std
        return max(-self.clip, min(self.clip, z))

    def transform_row(self, row: Mapping[str, float]) -> Dict[str, float]:
        return {k: self.transform(k, v) for k, v in row.items()}

    def zscored(self, name: str) -> List[float]:
        return zscore_clip(self._store.get(name, []), clip=self.clip)

    def stats(self) -> Dict[str, Tuple[float, float]]:
        return dict(self._stats)


def normalize_batch(rows: Sequence[Mapping[str, float]], clip: float = 3.0) -> List[Dict[str, float]]:
    """Convenience: z-score each key across the batch."""
    if not rows:
        return []
    keys = rows[0].keys()
    norm = GenerationNormalizer(clip=clip)
    for row in rows:
        norm.add_row(row)
    norm.fit()
    return [norm.transform_row(row) for row in rows]
