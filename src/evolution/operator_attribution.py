"""Operator utility statistics & counterfactual comparison (Phase5-Audit-2).

Answers: does PEEM learn causal operator contribution, or merely correlate
with successful offspring?

- Observational utilities from archive/experience (correlational)
- Counterfactual probe: same parent, every mutation type, compare deltas
- Bootstrap confidence intervals on operator utility
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.evolution.adaptive_mutation import default_registry
from src.evolution.credit_assignment import objective_improvement


@dataclass
class OperatorStats:
    name: str
    n: int
    mean_improvement: float
    std_improvement: float
    mean_pareto_gain: float
    success_rate: float
    ci_low: float
    ci_high: float
    kind: str = "observational"  # or counterfactual

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "n": self.n,
            "mean_improvement": self.mean_improvement,
            "std_improvement": self.std_improvement,
            "mean_pareto_gain": self.mean_pareto_gain,
            "success_rate": self.success_rate,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "kind": self.kind,
        }


def _mean_std(xs: Sequence[float]) -> Tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / n
    return m, math.sqrt(var)


def bootstrap_ci(
    xs: Sequence[float],
    *,
    n_boot: int = 500,
    alpha: float = 0.05,
    seed: int = 0,
) -> Tuple[float, float]:
    """Percentile bootstrap CI for the mean."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return float(xs[0]), float(xs[0])
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [xs[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return float(lo), float(hi)


def observational_operator_stats(
    records: Sequence[Any],
    *,
    kind: str = "observational",
) -> Dict[str, OperatorStats]:
    """Aggregate EvolutionRecord-like objects by mutation_type."""
    buckets: Dict[str, List[float]] = {}
    gains: Dict[str, List[float]] = {}
    success: Dict[str, List[float]] = {}
    for r in records:
        t = str(getattr(r, "mutation_type", "unknown"))
        imp = objective_improvement(
            getattr(r, "parent_objectives", []) or [],
            getattr(r, "child_objectives", []) or [],
        )
        buckets.setdefault(t, []).append(imp)
        hv = float(getattr(r, "hypervolume_contribution", 0.0) or 0.0)
        gains.setdefault(t, []).append(hv)
        success.setdefault(t, []).append(1.0 if getattr(r, "success", False) else 0.0)
    out: Dict[str, OperatorStats] = {}
    for t, imps in buckets.items():
        m, s = _mean_std(imps)
        lo, hi = bootstrap_ci(imps, seed=hash(t) & 0xFFFF)
        out[t] = OperatorStats(
            name=t,
            n=len(imps),
            mean_improvement=m,
            std_improvement=s,
            mean_pareto_gain=_mean_std(gains.get(t, [0.0]))[0],
            success_rate=_mean_std(success.get(t, [0.0]))[0],
            ci_low=lo,
            ci_high=hi,
            kind=kind,
        )
    return out


def counterfactual_probe(
    parents: Sequence[AgentGenome],
    evaluate: Callable[[AgentGenome], Sequence[float]],
    *,
    seed: int = 0,
    n_repeats: int = 3,
) -> Dict[str, OperatorStats]:
    """Apply every mutation type to the same parents; measure Δobjective.

    This is *interventional* (do-operator), stronger than observational credit.
    """
    rng = random.Random(seed)
    registry = default_registry()
    names = registry.names()
    samples: Dict[str, List[float]] = {t: [] for t in names}
    paretos: Dict[str, List[float]] = {t: [] for t in names}

    for parent in parents:
        base = list(evaluate(parent))
        for t in names:
            for _ in range(n_repeats):
                child = registry.apply(t, parent, rng, rate=1.0)
                if child == parent:
                    continue
                vals = list(evaluate(child))
                imp = objective_improvement(base, vals)
                samples[t].append(imp)
                # Simple Pareto gain: child mixed-dominates parent
                from src.utils.pareto import dominates_mixed

                paretos[t].append(1.0 if dominates_mixed(vals, base) else 0.0)

    out: Dict[str, OperatorStats] = {}
    for t in names:
        imps = samples[t]
        m, s = _mean_std(imps)
        lo, hi = bootstrap_ci(imps, seed=seed + 1)
        out[t] = OperatorStats(
            name=t,
            n=len(imps),
            mean_improvement=m,
            std_improvement=s,
            mean_pareto_gain=_mean_std(paretos[t])[0],
            success_rate=_mean_std(paretos[t])[0],
            ci_low=lo,
            ci_high=hi,
            kind="counterfactual",
        )
    return out


def attribution_verdict(
    observational: Dict[str, OperatorStats],
    counterfactual: Dict[str, OperatorStats],
) -> Dict[str, Any]:
    """Compare observational vs interventional ranking."""
    obs_rank = sorted(observational.items(), key=lambda kv: -kv[1].mean_improvement)
    cf_rank = sorted(counterfactual.items(), key=lambda kv: -kv[1].mean_improvement)
    obs_order = [k for k, _ in obs_rank]
    cf_order = [k for k, _ in cf_rank]
    # Spearman-like agreement on top-1
    top_match = bool(obs_order) and bool(cf_order) and obs_order[0] == cf_order[0]
    # CIs overlapping zero => not distinguishable
    null_safe = [
        t for t, st in counterfactual.items()
        if st.ci_low <= 0.0 <= st.ci_high
    ]
    return {
        "observational_ranking": obs_order,
        "counterfactual_ranking": cf_order,
        "top1_agreement": top_match,
        "counterfactual_null_operators": null_safe,
        "causal_claim_supported": top_match and len(null_safe) < len(counterfactual),
        "interpretation": (
            "PEEM scores are correlated with offspring success by construction; "
            "counterfactual intervention shows which operators truly improve objectives. "
            "Agreement supports (but does not prove) causal utility; disagreement "
            "implies observational credit is partially confounded."
        ),
    }
