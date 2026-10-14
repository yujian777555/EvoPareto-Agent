"""Mutation credit assignment (Phase 2.5).

Composite Mutation Value:

    MV = α * improvement
       + β * hypervolume_gain
       + γ * diversity_gain
       + δ * survival_credit

Improvement uses mixed-direction objective gains; HV contribution and
diversity are computed against the offspring/parent population; survival
reflects NSGA-III retention into the next generation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.evaluation.metrics import hypervolume
from src.evolution.diversity import diversity_contribution
from src.utils.pareto import dominates_mixed


# Weights sum to 1.0 for interpretability.
DEFAULT_WEIGHTS = {
    "improvement": 0.35,
    "hypervolume": 0.30,
    "diversity": 0.20,
    "survival": 0.15,
}


@dataclass
class CreditWeights:
    alpha: float = DEFAULT_WEIGHTS["improvement"]   # improvement
    beta: float = DEFAULT_WEIGHTS["hypervolume"]    # hypervolume gain
    gamma: float = DEFAULT_WEIGHTS["diversity"]     # diversity gain
    delta: float = DEFAULT_WEIGHTS["survival"]      # survival credit

    def normalized(self) -> "CreditWeights":
        s = self.alpha + self.beta + self.gamma + self.delta
        if s <= 0:
            return CreditWeights(0.25, 0.25, 0.25, 0.25)
        return CreditWeights(self.alpha / s, self.beta / s, self.gamma / s, self.delta / s)


@dataclass
class CreditBreakdown:
    improvement: float
    hypervolume_gain: float
    diversity_gain: float
    survival_credit: float
    pareto_rank_change: int
    hypervolume_contribution: float
    diversity_contribution: float
    survived_next_generation: bool
    mutation_value: float

    def to_dict(self) -> dict:
        return {
            "improvement": self.improvement,
            "hypervolume_gain": self.hypervolume_gain,
            "diversity_gain": self.diversity_gain,
            "survival_credit": self.survival_credit,
            "pareto_rank_change": self.pareto_rank_change,
            "hypervolume_contribution": self.hypervolume_contribution,
            "diversity_contribution": self.diversity_contribution,
            "survived_next_generation": self.survived_next_generation,
            "mutation_value": self.mutation_value,
        }


def objective_improvement(
    parent: Sequence[float],
    child: Sequence[float],
) -> float:
    """Signed improvement in paper semantics.

    Positive part of mixed-direction gains, normalized by dimension.
    For cost (minimize), a decrease is a gain.
    """
    # Mixed gain: for maximize obj, child-parent; for cost, parent-child.
    gains = []
    for i, (p, c) in enumerate(zip(parent, child)):
        if i == 2:  # cost
            gains.append(float(p) - float(c))
        else:
            gains.append(float(c) - float(p))
    pos = sum(max(0.0, g) for g in gains)
    neg = sum(max(0.0, -g) for g in gains)
    return (pos - 0.5 * neg) / max(1, len(parent))


def pareto_rank_change(
    parent_rank: int,
    child_rank: int,
) -> int:
    """Positive if child is on a better (lower-index) front."""
    return int(parent_rank) - int(child_rank)


def hypervolume_contribution(
    child: Sequence[float],
    front: Sequence[Sequence[float]],
    *,
    n_samples: int = 512,
    seed: int = 0,
) -> float:
    """Marginal HV of adding `child` to `front`."""
    if not front:
        return float(hypervolume([child], n_samples=n_samples, seed=seed))
    hv_before = hypervolume(front, n_samples=n_samples, seed=seed)
    hv_after = hypervolume(list(front) + [list(child)], n_samples=n_samples, seed=seed)
    return float(hv_after - hv_before)


def survival_credit(survived: bool) -> float:
    return 1.0 if survived else 0.0


def compute_credit(
    parent: Sequence[float],
    child: Sequence[float],
    *,
    population_front: Optional[Sequence[Sequence[float]]] = None,
    parent_rank: int = 1,
    child_rank: int = 1,
    survived: bool = False,
    weights: Optional[CreditWeights] = None,
    hv_n_samples: int = 256,
    seed: int = 0,
) -> CreditBreakdown:
    """Full Pareto-aware credit for one mutation transition."""
    w = (weights or CreditWeights()).normalized()

    imp = objective_improvement(parent, child)
    hv_gain = hypervolume_contribution(
        child,
        list(population_front or []),
        n_samples=hv_n_samples,
        seed=seed,
    )
    # Normalize HV gain into roughly [0, 1] with a soft clip.
    hv_n = math.tanh(max(0.0, hv_gain) * 10.0)
    if hv_gain < 0:
        hv_n = -math.tanh(-hv_gain * 10.0)

    div = diversity_contribution(child, list(population_front or []) or [list(parent)])
    div_n = max(0.0, min(2.0, div)) / 2.0

    surv = survival_credit(survived)

    mv = (
        w.alpha * max(-1.0, min(1.0, imp))
        + w.beta * hv_n
        + w.gamma * div_n
        + w.delta * surv
    )

    return CreditBreakdown(
        improvement=imp,
        hypervolume_gain=hv_gain,
        diversity_gain=div_n,
        survival_credit=surv,
        pareto_rank_change=pareto_rank_change(parent_rank, child_rank),
        hypervolume_contribution=hv_gain,
        diversity_contribution=div,
        survived_next_generation=bool(survived),
        mutation_value=float(mv),
    )
