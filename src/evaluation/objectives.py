"""Objective conventions for Phase 0 multi-objective agent search.

Five objectives (maximization semantics as named by the paper draft):

    [performance, efficiency, cost, robustness, autonomy]

NSGA-III internally minimizes, so we convert with `to_minimization`:

    [-performance, -efficiency, cost, -robustness, -autonomy]
"""

from __future__ import annotations

from typing import List, Sequence

OBJECTIVE_NAMES = (
    "performance",
    "efficiency",
    "cost",
    "robustness",
    "autonomy",
)

# True if larger raw value is better.
MAXIMIZE = (True, True, False, True, True)

N_OBJECTIVES = len(OBJECTIVE_NAMES)


def to_minimization(fitness: Sequence[float]) -> List[float]:
    """Convert raw fitness (paper semantics) to NSGA-III minimization space."""
    if len(fitness) != N_OBJECTIVES:
        raise ValueError(f"expected {N_OBJECTIVES} objectives, got {len(fitness)}")
    return [
        -float(v) if maximize else float(v)
        for v, maximize in zip(fitness, MAXIMIZE)
    ]


def to_maximization(minimized: Sequence[float]) -> List[float]:
    """Inverse of `to_minimization`."""
    if len(minimized) != N_OBJECTIVES:
        raise ValueError(f"expected {N_OBJECTIVES} objectives, got {len(minimized)}")
    return [
        -float(v) if maximize else float(v)
        for v, maximize in zip(minimized, MAXIMIZE)
    ]
