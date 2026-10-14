"""Pareto-set utilities used by experiments and tests."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from src.evaluation.objectives import MAXIMIZE, to_minimization


def dominates_max(a: Sequence[float], b: Sequence[float]) -> bool:
    """True if a dominates b under maximization (all objectives)."""
    strictly_better = False
    for x, y in zip(a, b):
        if x < y:
            return False
        if x > y:
            strictly_better = True
    return strictly_better


def dominates_min(a: Sequence[float], b: Sequence[float]) -> bool:
    strictly_better = False
    for x, y in zip(a, b):
        if x > y:
            return False
        if x < y:
            strictly_better = True
    return strictly_better


def dominates_mixed(a: Sequence[float], b: Sequence[float]) -> bool:
    """Dominance under paper semantics (max except cost)."""
    return dominates_min(to_minimization(a), to_minimization(b))


def pareto_mask_max(rows: Sequence[Sequence[float]]) -> List[bool]:
    """Boolean mask of non-dominated rows under maximization (all objectives)."""
    n = len(rows)
    mask = [True] * n
    for i in range(n):
        if not mask[i]:
            continue
        for j in range(n):
            if i == j or not mask[j]:
                continue
            if dominates_max(rows[j], rows[i]):
                mask[i] = False
                break
            if dominates_max(rows[i], rows[j]):
                mask[j] = False
    return mask


def pareto_mask_mixed(rows: Sequence[Sequence[float]]) -> List[bool]:
    """Boolean mask of non-dominated rows under paper max/min semantics."""
    n = len(rows)
    mask = [True] * n
    for i in range(n):
        if not mask[i]:
            continue
        for j in range(n):
            if i == j or not mask[j]:
                continue
            if dominates_mixed(rows[j], rows[i]):
                mask[i] = False
                break
            if dominates_mixed(rows[i], rows[j]):
                mask[j] = False
    return mask


def filter_pareto_max(rows: Sequence[Sequence[float]]) -> List[List[float]]:
    mask = pareto_mask_max(rows)
    return [list(rows[i]) for i in range(len(rows)) if mask[i]]


def filter_pareto_mixed(rows: Sequence[Sequence[float]]) -> List[List[float]]:
    mask = pareto_mask_mixed(rows)
    return [list(rows[i]) for i in range(len(rows)) if mask[i]]


def hypervolume_2d_max(
    front: Sequence[Sequence[float]], ref: Sequence[float]
) -> float:
    """Exact 2D hypervolume for maximization (for simple sanity checks)."""
    pts = [(float(p[0]), float(p[1])) for p in front]
    # Keep only points that dominate the reference.
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
