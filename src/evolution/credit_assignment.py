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
    spec: Optional[Any] = None,
) -> float:
    """Signed improvement using ObjectiveSpec directions (default 5-obj)."""
    if spec is not None:
        return spec.improvement(parent, child)
    from src.evaluation.objective_spec import SPEC_5

    return SPEC_5.improvement(parent, child)


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
    n_samples: int = 64,
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


# ====================================================================== #
# Phase 2.5-R1: robust rank-based + z-normalized composite value
# ====================================================================== #
@dataclass
class RobustCreditBreakdown:
    improvement: float
    pareto_score: float
    diversity_score: float
    survival_score: float
    improvement_norm: float = 0.0
    pareto_norm: float = 0.0
    diversity_norm: float = 0.0
    survival_norm: float = 0.0
    mutation_value: float = 0.0
    pareto_rank: int = 0

    def raw_row(self) -> dict:
        return {
            "improvement": self.improvement,
            "pareto": self.pareto_score,
            "diversity": self.diversity_score,
            "survival": self.survival_score,
        }

    def to_dict(self) -> dict:
        return {
            "improvement": self.improvement,
            "pareto_score": self.pareto_score,
            "diversity_score": self.diversity_score,
            "survival_score": self.survival_score,
            "improvement_norm": self.improvement_norm,
            "pareto_norm": self.pareto_norm,
            "diversity_norm": self.diversity_norm,
            "survival_norm": self.survival_norm,
            "mutation_value": self.mutation_value,
            "pareto_rank": self.pareto_rank,
        }


def robust_raw_components(
    parent: Sequence[float],
    child: Sequence[float],
    *,
    population: Optional[Sequence[Sequence[float]]] = None,
    survived: bool = False,
    pareto_score: Optional[float] = None,
    spec: Optional[Any] = None,
) -> RobustCreditBreakdown:
    """Compute raw (un-normalized) components for robust PEEM."""
    from src.evolution.diversity import diversity_contribution
    from src.evolution.pareto_credit import ParetoContributionEstimator

    imp = objective_improvement(parent, child, spec=spec)
    if pareto_score is None:
        est = ParetoContributionEstimator()
        pareto_score = est.score_one(parent, child, list(population or []))
    div = diversity_contribution(child, list(population or []) or [list(parent)])
    div_n = max(0.0, min(2.0, div)) / 2.0
    surv = survival_credit(survived)
    return RobustCreditBreakdown(
        improvement=imp,
        pareto_score=float(pareto_score),
        diversity_score=float(div_n),
        survival_score=surv,
    )


def apply_normalized_mv(
    raw: RobustCreditBreakdown,
    *,
    weights: Optional[CreditWeights] = None,
    delayed_bonus: float = 0.0,
) -> RobustCreditBreakdown:
    """MV = α·imp_n + β·pareto_n + γ·div_n + δ·surv_n  (higher = better)."""
    w = (weights or CreditWeights()).normalized()
    raw.improvement_norm = max(-3.0, min(3.0, raw.improvement))
    raw.pareto_norm = raw.pareto_score  # already in {0, 0.5, 1.0}
    raw.diversity_norm = raw.diversity_score
    raw.survival_norm = raw.survival_score
    raw.mutation_value = (
        w.alpha * raw.improvement_norm
        + w.beta * raw.pareto_norm
        + w.gamma * raw.diversity_norm
        + w.delta * raw.survival_norm
        + delayed_bonus
    )
    return raw


def compute_robust_credit(
    parent: Sequence[float],
    child: Sequence[float],
    *,
    population: Optional[Sequence[Sequence[float]]] = None,
    survived: bool = False,
    pareto_score: Optional[float] = None,
    weights: Optional[CreditWeights] = None,
    delayed_bonus: float = 0.0,
) -> RobustCreditBreakdown:
    raw = robust_raw_components(
        parent,
        child,
        population=population,
        survived=survived,
        pareto_score=pareto_score,
    )
    return apply_normalized_mv(raw, weights=weights, delayed_bonus=delayed_bonus)
