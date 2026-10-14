"""Population diversity metrics for Pareto-aware credit assignment.

Supports crowding distance (NSGA-II style) and spacing metric.
All functions accept **paper-semantics** objective vectors (mixed max/min)
and convert internally where needed.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

from src.evaluation.objectives import to_minimization
from src.utils.pareto import pareto_mask_mixed


def crowding_distance(
    rows: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> List[float]:
    """NSGA-II crowding distance on the given points (same front or any set).

    Larger value => more isolated / boundary => higher diversity contribution.
    Returns a list aligned with `rows`.
    """
    n = len(rows)
    if n == 0:
        return []
    if n <= 2:
        return [math.inf] * n

    min_rows = [to_minimization(r) for r in rows] if maximize_input else [list(map(float, r)) for r in rows]
    m = len(min_rows[0])
    dist = [0.0] * n

    for j in range(m):
        order = sorted(range(n), key=lambda i: min_rows[i][j])
        dist[order[0]] = math.inf
        dist[order[-1]] = math.inf
        f_min = min_rows[order[0]][j]
        f_max = min_rows[order[-1]][j]
        span = f_max - f_min
        if span <= 1e-12:
            continue
        for k in range(1, n - 1):
            i = order[k]
            if math.isinf(dist[i]):
                continue
            prev_v = min_rows[order[k - 1]][j]
            next_v = min_rows[order[k + 1]][j]
            dist[i] += (next_v - prev_v) / span
    return dist


def spacing(rows: Sequence[Sequence[float]], *, maximize_input: bool = True) -> float:
    """Schott spacing metric (smaller = more uniform)."""
    n = len(rows)
    if n < 2:
        return 0.0
    min_rows = [to_minimization(r) for r in rows] if maximize_input else [list(map(float, r)) for r in rows]
    m = len(min_rows[0])
    d_list: List[float] = []
    for i in range(n):
        best = math.inf
        for j in range(n):
            if i == j:
                continue
            s = sum(abs(min_rows[i][k] - min_rows[j][k]) for k in range(m))
            if s < best:
                best = s
        d_list.append(best)
    d_bar = sum(d_list) / n
    var = sum((d - d_bar) ** 2 for d in d_list) / n
    return math.sqrt(var)


def spread(
    rows: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> float:
    """Simple diversity score in [0, 1]-ish: mean normalized crowding."""
    if not rows:
        return 0.0
    cd = crowding_distance(rows, maximize_input=maximize_input)
    finite = [c for c in cd if not math.isinf(c)]
    if not finite:
        return 1.0
    return float(sum(finite) / len(finite))


def diversity_contribution(
    candidate: Sequence[float],
    population: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> float:
    """How much `candidate` extends diversity of `population`.

    Uses nearest-neighbor distance in minimization space, normalized by
    the population's mean nearest-neighbor distance. >1 means more isolated
    than average (good for coverage).
    """
    if not population:
        return 1.0
    cand = to_minimization(candidate) if maximize_input else list(map(float, candidate))
    pop = [to_minimization(r) for r in population] if maximize_input else [list(map(float, r)) for r in population]

    def nn_dist(vec: Sequence[float], pool: Sequence[Sequence[float]]) -> float:
        best = math.inf
        for p in pool:
            s = 0.0
            for k in range(len(vec)):
                d = vec[k] - p[k]
                s += d * d
            if s < best:
                best = s
        return best ** 0.5

    d_cand = nn_dist(cand, pop)
    if math.isinf(d_cand):
        return 1.5
    # Cheap estimate of typical spacing: mean NN over a sample of the pool.
    sample = pop if len(pop) <= 12 else pop[:: max(1, len(pop) // 12)]
    d_others = []
    for i, p in enumerate(sample):
        rest = sample[:i] + sample[i + 1 :]
        if not rest:
            continue
        d_others.append(nn_dist(p, rest))
    if not d_others:
        return 1.0
    mean_d = sum(d_others) / len(d_others)
    if mean_d <= 1e-12:
        return 1.0 if d_cand > 1e-12 else 0.0
    return float(min(3.0, d_cand / mean_d))


def non_dominated_diversity(
    rows: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> float:
    """Composite diversity of a front: spacing (inv) + crowding mean."""
    if not rows:
        return 0.0
    mask = pareto_mask_mixed(rows) if maximize_input else [True] * len(rows)
    front = [rows[i] for i in range(len(rows)) if mask[i]]
    if len(front) < 2:
        return 0.0
    sp = spacing(front, maximize_input=maximize_input)
    spr = spread(front, maximize_input=maximize_input)
    # Higher is better.
    return float(spr / (1.0 + sp))
