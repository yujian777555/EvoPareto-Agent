"""Multi-objective quality metrics (Phase 2).

`hypervolume(front)` is the primary metric for evolution-memory demos.
Paper-semantics vectors (mixed max/min) are converted internally.
"""

from __future__ import annotations

import math
import random
from typing import List, Optional, Sequence

from src.evaluation.objectives import to_minimization
from src.utils.pareto import dominates_min, pareto_mask_mixed


def pareto_front_size(rows: Sequence[Sequence[float]]) -> int:
    return sum(1 for m in pareto_mask_mixed(rows) if m)


def hypervolume(
    front: Sequence[Sequence[float]],
    ref: Optional[Sequence[float]] = None,
    *,
    maximize_input: bool = True,
    n_samples: int = 20000,
    seed: int = 0,
) -> float:
    """Hypervolume indicator of `front` w.r.t. reference `ref`.

    Parameters
    ----------
    front:
        Objective vectors in paper semantics by default (max except cost).
        Pass `maximize_input=False` if already in minimization space.
    ref:
        Reference point in the same space as `front`. If omitted, a weak
        reference slightly beyond the front nadir is used.
    n_samples / seed:
        Monte-Carlo estimate for dimension > 2; exact staircase for 2D.

    Returns
    -------
    float
        HV >= 0 (larger is better).
    """
    if not front:
        return 0.0
    dim = len(front[0])
    if dim < 1:
        raise ValueError("front points must be non-empty vectors")

    min_rows = [to_minimization(p) for p in front] if maximize_input else [list(map(float, p)) for p in front]

    if ref is None:
        # Weak reference in paper semantics: worst corner
        # (0 performance/efficiency/robustness/autonomy, cost=1).
        if maximize_input:
            ref_min = to_minimization([0.0, 0.0, 1.0, 0.0, 0.0][:dim]) if dim == 5 else _default_ref_min(min_rows)
        else:
            ref_min = _default_ref_min(min_rows)
    else:
        ref_min = to_minimization(ref) if maximize_input else list(map(float, ref))

    kept = [r for r in min_rows if all(r[j] < ref_min[j] for j in range(dim))]
    if not kept:
        return 0.0
    kept = _filter_min_front(kept)

    if dim == 1:
        return max(0.0, ref_min[0] - min(r[0] for r in kept))
    if dim == 2:
        return _hv_2d_min_staircase(kept, ref_min)
    return _hv_mc_min(kept, ref_min, n_samples=n_samples, seed=seed)


def _filter_min_front(rows: Sequence[Sequence[float]]) -> List[List[float]]:
    out: List[List[float]] = []
    for i, r in enumerate(rows):
        if any(dominates_min(o, r) for j, o in enumerate(rows) if i != j):
            continue
        out.append(list(r))
    return out


def _default_ref_min(rows: Sequence[Sequence[float]]) -> List[float]:
    """Weak ref slightly beyond nadir in minimization space."""
    dim = len(rows[0])
    nadir = [max(r[j] for r in rows) for j in range(dim)]
    ideal = [min(r[j] for r in rows) for j in range(dim)]
    span = [max(nadir[j] - ideal[j], 1e-6) for j in range(dim)]
    return [nadir[j] + 0.1 * span[j] for j in range(dim)]


def _hv_2d_min_staircase(rows: Sequence[Sequence[float]], ref: Sequence[float]) -> float:
    """Exact 2D HV under minimization via a staircase sweep."""
    pts = sorted({(float(x), float(y)) for x, y in rows})
    stair: List[tuple] = []
    for x, y in pts:
        while stair and stair[-1][1] >= y:
            stair.pop()
        stair.append((x, y))

    hv = 0.0
    for i in range(len(stair)):
        x, y = stair[i]
        x_next = ref[0] if i == len(stair) - 1 else stair[i + 1][0]
        if y < ref[1] and x_next > x:
            hv += (x_next - x) * (ref[1] - y)
    return hv


def _hv_mc_min(
    rows: Sequence[Sequence[float]],
    ref: Sequence[float],
    *,
    n_samples: int = 20000,
    seed: int = 0,
) -> float:
    """Monte-Carlo HV for minimization over box [ideal, ref]."""
    dim = len(ref)
    ideal = [min(r[j] for r in rows) for j in range(dim)]
    span = [ref[j] - ideal[j] for j in range(dim)]
    if any(s <= 0 for s in span):
        return 0.0
    rng = random.Random(seed)
    pts = [tuple(r) for r in rows]
    hit = 0
    for _ in range(n_samples):
        x = [ideal[j] + rng.random() * span[j] for j in range(dim)]
        for p in pts:
            if all(p[j] <= x[j] for j in range(dim)) and any(p[j] < x[j] for j in range(dim)):
                hit += 1
                break
    volume = 1.0
    for s in span:
        volume *= s
    return volume * (hit / float(n_samples))


def hypervolume_2d_max(
    front: Sequence[Sequence[float]], ref: Sequence[float]
) -> float:
    """Exact 2D HV under maximization (thin wrapper for call-site clarity)."""
    pts = [(float(p[0]), float(p[1])) for p in front]
    pts = [(x, y) for x, y in pts if x > ref[0] and y > ref[1]]
    if not pts:
        return 0.0
    pts.sort(key=lambda p: p[0], reverse=True)
    area = 0.0
    prev_y = ref[1]
    for x, y in pts:
        if y <= prev_y:
            continue
        area += (x - ref[0]) * (y - prev_y)
        prev_y = y
    return area


# ====================================================================== #
# Phase 2.5: IGD / Spacing / Mutation entropy
# ====================================================================== #
def igd(
    front: Sequence[Sequence[float]],
    reference_front: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> float:
    """Inverted Generational Distance (smaller is better).

    Mean distance from each reference point to the nearest front point.
    """
    if not reference_front:
        return 0.0
    if not front:
        return float("inf")

    def to_min(rows):
        return [to_minimization(r) for r in rows] if maximize_input else [list(map(float, r)) for r in rows]

    f = to_min(front)
    r = to_min(reference_front)
    dim = len(r[0])
    total = 0.0
    for rp in r:
        best = min(sum((rp[k] - fp[k]) ** 2 for k in range(dim)) ** 0.5 for fp in f)
        total += best
    return total / len(r)


def spacing(
    front: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> float:
    """Schott spacing (smaller = more uniform). Re-exported convenience."""
    from src.evolution.diversity import spacing as _spacing

    return _spacing(front, maximize_input=maximize_input)


def mutation_entropy(counts: Sequence[int]) -> float:
    """Shannon entropy of mutation-type usage in bits (higher = more diverse)."""
    total = sum(int(c) for c in counts)
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts:
        if c <= 0:
            continue
        p = c / total
        h -= p * math.log2(p)
    return float(h)


def normalized_mutation_entropy(counts: Sequence[int]) -> float:
    """Entropy / log2(n), in [0, 1] for n>1 types."""
    n = sum(1 for c in counts if c > 0)
    if n <= 1:
        return 0.0
    return mutation_entropy(counts) / math.log2(n)


def reference_front_from_population(
    rows: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> List[List[float]]:
    """Empirical reference front = mixed non-dominated set of `rows`."""
    mask = pareto_mask_mixed(rows) if maximize_input else [True] * len(rows)
    return [list(rows[i]) for i in range(len(rows)) if mask[i]]
