"""Rank-based Pareto contribution estimator (Phase 2.5-R1).

Replaces noisy Monte-Carlo hypervolume deltas with **rank buckets**:

    top 20%    → 1.0
    middle 50% → 0.5
    bottom 30% → 0.0

No dependence on exact HV values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from src.utils.pareto import dominates_mixed, pareto_mask_mixed


# Bucket scores required by the spec.
TOP_SCORE = 1.0
MID_SCORE = 0.5
LOW_SCORE = 0.0

TOP_FRAC = 0.20
MID_FRAC = 0.50  # middle 50% → 0.5; remaining 30% → 0


def rank_bucket_score(rank_ratio: float) -> float:
    """Map a [0, 1] rank ratio (0 = best) to a bucket score."""
    r = min(1.0, max(0.0, float(rank_ratio)))
    if r < TOP_FRAC:
        return TOP_SCORE
    if r < TOP_FRAC + MID_FRAC:
        return MID_SCORE
    return LOW_SCORE


def pareto_rank_of(child: Sequence[float], others: Sequence[Sequence[float]]) -> int:
    """0 = non-dominated vs others; higher = dominated by more layers."""
    pool = [list(child)] + [list(o) for o in others]
    # Simple peel: count how many others dominate child (approx rank).
    rank = 0
    remaining = [list(o) for o in others]
    current = list(child)
    while True:
        dominators = [o for o in remaining if dominates_mixed(o, current)]
        if not dominators:
            break
        rank += 1
        # Peel one layer: drop points dominated by this layer's non-dominated set.
        mask = pareto_mask_mixed(dominators)
        remaining = [dominators[i] for i in range(len(dominators)) if not mask[i]]
        if not remaining or rank > 20:
            break
        current = list(child)
    return rank


def dominance_count(child: Sequence[float], others: Sequence[Sequence[float]]) -> int:
    return sum(1 for o in others if dominates_mixed(o, child))


def contribution_from_improvement_and_ranks(
    parent: Sequence[float],
    child: Sequence[float],
    population: Sequence[Sequence[float]],
    offspring_scores: Optional[Sequence[float]] = None,
) -> Tuple[float, int]:
    """Return (bucket_score, pareto_rank).

    Rank is estimated within the offspring batch when `offspring_scores` is
    given (score of this child in the same batch), else vs the population.
    """
    rank = pareto_rank_of(child, population) if population else 0
    if offspring_scores is not None and len(offspring_scores) > 1:
        # Rank by improvement-based score within the offspring batch.
        order = sorted(offspring_scores, reverse=True)  # higher better
        try:
            idx = order.index(max(offspring_scores))  # placeholder, caller uses ranks
        except ValueError:
            idx = 0
    # Prefer rank ratio from population dominance among children vs pop.
    n = max(1, len(population) + 1)
    # If child is non-dominated against the whole pool, it is top-tier.
    if rank == 0:
        ratio = 0.0
    else:
        # Approximate ratio: rank / max_layers
        ratio = min(1.0, rank / 5.0)
    return rank_bucket_score(ratio), rank


@dataclass
class ParetoContributionEstimator:
    """Batch rank-based mutation contribution scores.

    Usage:
        est = ParetoContributionEstimator()
        scores = est.score_batch(parents, children, population)
    """

    top_frac: float = TOP_FRAC
    mid_frac: float = MID_FRAC

    def bucket(self, rank_ratio: float) -> float:
        r = min(1.0, max(0.0, float(rank_ratio)))
        if r < self.top_frac:
            return TOP_SCORE
        if r < self.top_frac + self.mid_frac:
            return MID_SCORE
        return LOW_SCORE

    def score_batch(
        self,
        parents: Sequence[Sequence[float]],
        children: Sequence[Sequence[float]],
        population: Sequence[Sequence[float]],
    ) -> List[float]:
        """One contribution score per (parent, child) pair.

        Strategy:
        1. Improvement signal per child (mixed-direction).
        2. Rank children within the batch by improvement.
        3. Map rank ratio → bucket score (1.0 / 0.5 / 0.0).
        """
        n = len(children)
        if n == 0:
            return []
        imps = []
        for i in range(n):
            p = parents[i] if i < len(parents) else children[i]
            imps.append(_improvement(p, children[i]))

        order = sorted(range(n), key=lambda i: imps[i], reverse=True)
        rank_of = {idx: r for r, idx in enumerate(order)}
        out = []
        for i in range(n):
            ratio = rank_of[i] / max(1, n - 1) if n > 1 else 0.0
            out.append(self.bucket(ratio))
        return out

    def score_one(
        self,
        parent: Sequence[float],
        child: Sequence[float],
        population: Sequence[Sequence[float]],
    ) -> float:
        """Single-child fallback: dominance-based rank vs population."""
        if not population:
            return MID_SCORE
        dom = dominance_count(child, population)
        n = len(population)
        if dom == 0:
            return TOP_SCORE
        if dom >= max(1, int(math.ceil(n * self.top_frac))) and dom / n >= 0.5:
            return LOW_SCORE
        if dom / n <= self.top_frac:
            return TOP_SCORE
        return MID_SCORE


def _improvement(parent: Sequence[float], child: Sequence[float]) -> float:
    gains = []
    for i, (p, c) in enumerate(zip(parent, child)):
        gains.append((float(p) - float(c)) if i == 2 else (float(c) - float(p)))
    return sum(gains) / max(1, len(gains))
