"""Exact 2D hypervolume for mixed directions (Phase5-R3-R5-R2 P1-E).

performance maximize, cost minimize, fixed reference point.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple


def hypervolume_2d_mixed(
    points: Sequence[Sequence[float]],
    ref: Sequence[float],
) -> float:
    """Exact 2D HV for (performance↑, cost↓) with reference (p_ref, c_ref).

    A point (s, c) dominates rectangle [ref.p, s] x [c, ref.c] in transformed
    space where lower cost is better. We transform cost' = -cost so both
    maximize, or compute directly:

        width  = s - ref_s   (only if s > ref_s)
        height = ref_c - c   (only if c < ref_c)
    """
    if len(ref) != 2:
        raise ValueError("ref must be 2D")
    ref_s, ref_c = float(ref[0]), float(ref[1])
    # Filter points that improve on ref.
    pts = []
    for p in points:
        if len(p) != 2:
            raise ValueError("points must be 2D")
        s, c = float(p[0]), float(p[1])
        if s > ref_s and c < ref_c:
            pts.append((s, c))
    if not pts:
        return 0.0
    # Keep non-dominated (under mixed): higher s and lower c better.
    nd: List[Tuple[float, float]] = []
    for i, (s, c) in enumerate(pts):
        dominated = False
        for j, (s2, c2) in enumerate(pts):
            if i == j:
                continue
            if s2 >= s and c2 <= c and (s2 > s or c2 < c):
                dominated = True
                break
        if not dominated:
            nd.append((s, c))
    # Sort by success descending; sweep cost.
    nd.sort(key=lambda x: (-x[0], x[1]))
    hv = 0.0
    prev_c = ref_c
    for s, c in nd:
        if c >= prev_c:
            continue
        hv += (s - ref_s) * (prev_c - c)
        prev_c = c
    return hv


def reference_point_default(cost_scale: float = 0.20) -> Tuple[float, float]:
    """Pre-registered 2D ref: performance=0, cost=cost_scale (worse than typical)."""
    return (0.0, float(cost_scale))
