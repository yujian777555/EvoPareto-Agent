"""Objective conventions for Phase 0 multi-objective agent search.

Five objectives (maximization semantics as named by the paper draft):

    [performance, efficiency, cost, robustness, autonomy]

NSGA-III internally minimizes, so we convert with `to_minimization`:

    [-performance, -efficiency, cost, -robustness, -autonomy]
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

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


def _maximize_flags(
    n: int, maximize: Optional[Sequence[bool]] = None
) -> Tuple[bool, ...]:
    if maximize is not None:
        flags = tuple(bool(x) for x in maximize)
        if len(flags) != n:
            raise ValueError(f"maximize length {len(flags)} != {n}")
        return flags
    if n == N_OBJECTIVES:
        return MAXIMIZE
    # Algorithmic tests with other dimensions default to all-maximize.
    return tuple(True for _ in range(n))


def to_minimization(
    fitness: Sequence[float], maximize: Optional[Sequence[bool]] = None
) -> List[float]:
    """Convert raw fitness (paper semantics) to NSGA-III minimization space."""
    flags = _maximize_flags(len(fitness), maximize)
    return [-float(v) if flag else float(v) for v, flag in zip(fitness, flags)]


def to_maximization(
    minimized: Sequence[float], maximize: Optional[Sequence[bool]] = None
) -> List[float]:
    """Inverse of `to_minimization`."""
    flags = _maximize_flags(len(minimized), maximize)
    return [-float(v) if flag else float(v) for v, flag in zip(minimized, flags)]
