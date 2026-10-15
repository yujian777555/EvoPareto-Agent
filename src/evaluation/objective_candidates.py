"""Candidate objective evaluators (Phase5-R3-R5) — NOT replacing paper defaults.

Versions:
  legacy_5obj    — current paper mapping (audit-invalid for eff/robust/auto)
  candidate_5obj — Plan A repaired formulas
  candidate_2obj — Plan B success + cost

Each evaluator is explicit about direction and raw vs transformed values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

VERSION_LEGACY_5 = "legacy_5obj"
VERSION_CAND_5 = "candidate_5obj"
VERSION_CAND_2 = "candidate_2obj"


@dataclass
class EpisodeStats:
    success: bool
    steps: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    max_steps: int = 30
    n_fallbacks: int = 0
    n_external_help: int = 0
    stalled: bool = False


def _sat_cost(c: float) -> float:
    return c / (c + 1.0)


class Legacy5Evaluator:
    version = VERSION_LEGACY_5
    names = ("performance", "efficiency", "cost", "robustness", "autonomy")
    maximize = (True, True, False, True, True)

    def evaluate(self, eps: Sequence[EpisodeStats]) -> List[float]:
        n = max(1, len(eps))
        perf = sum(1.0 for e in eps if e.success) / n
        eff = 1.0 / (
            1.0
            + sum(e.steps for e in eps) / n / 20.0
            + sum(e.tokens_in + e.tokens_out for e in eps) / n / 2000.0
        )
        cost = _sat_cost(sum(e.cost_usd for e in eps) / n)
        stall = sum(1.0 for e in eps if e.stalled) / n
        robust = perf * (1.0 - stall)
        early = 0.0
        auto = max(0.0, 1.0 - 0.5 * early - 0.3 * stall)
        return [perf, eff, cost, robust, auto]


class Candidate5Evaluator:
    """Plan A: success-conditioned efficiency, stability robustness, behavior autonomy."""

    version = VERSION_CAND_5
    names = ("performance", "efficiency", "cost", "robustness", "autonomy")
    maximize = (True, True, False, True, True)

    def evaluate(self, eps: Sequence[EpisodeStats]) -> List[float]:
        n = max(1, len(eps))
        perf = sum(1.0 for e in eps if e.success) / n
        # Efficiency: only successes get full resource score; failures penalized.
        eff_vals = []
        for e in eps:
            raw = 1.0 / (
                1.0 + e.steps / max(1, e.max_steps) + (e.tokens_in + e.tokens_out) / 2000.0
            )
            eff_vals.append(raw if e.success else 0.3 * raw)
        eff = sum(eff_vals) / n
        cost = _sat_cost(sum(e.cost_usd for e in eps) / n)
        # Robustness: success consistency across instances (variance penalty).
        flags = [1.0 if e.success else 0.0 for e in eps]
        mu = sum(flags) / n
        var = sum((f - mu) ** 2 for f in flags) / n
        robust = max(0.0, mu - 0.5 * var)
        # Autonomy: 1 - fallback_rate - external_help_rate
        fb = sum(e.n_fallbacks for e in eps) / n
        help_rate = sum(e.n_external_help for e in eps) / n
        steps = sum(max(1, e.steps) for e in eps) / n
        auto = max(0.0, 1.0 - (fb / steps) - 0.5 * (help_rate / steps))
        return [perf, eff, cost, robust, auto]


class Candidate2Evaluator:
    """Plan B: task success ↑ and inference cost ↓ only."""

    version = VERSION_CAND_2
    names = ("performance", "cost")
    maximize = (True, False)

    def evaluate(self, eps: Sequence[EpisodeStats]) -> List[float]:
        n = max(1, len(eps))
        perf = sum(1.0 for e in eps if e.success) / n
        cost = sum(e.cost_usd for e in eps) / n  # raw $, minimize
        return [perf, cost]

    @staticmethod
    def diagnostic(eps: Sequence[EpisodeStats]) -> Dict[str, float]:
        n = max(1, len(eps))
        return {
            "mean_steps": sum(e.steps for e in eps) / n,
            "mean_tokens": sum(e.tokens_in + e.tokens_out for e in eps) / n,
            "success_rate": sum(1.0 for e in eps if e.success) / n,
        }


def to_minimization(values: Sequence[float], maximize: Sequence[bool]) -> List[float]:
    return [-float(v) if m else float(v) for v, m in zip(values, maximize)]


def construction_cases() -> List[Dict[str, Any]]:
    """Offline cases 1–6 from the spec."""
    cases = []

    def stats(success, steps, cost, tokens=100):
        return EpisodeStats(success=success, steps=steps, tokens_in=tokens, tokens_out=20, cost_usd=cost)

    cases.append(("quick_fail", [stats(False, 1, 0.001)]))
    cases.append(("long_fail", [stats(False, 10, 0.01)]))
    cases.append(("success_15", [stats(True, 15, 0.01)]))
    cases.append(("success_30", [stats(True, 30, 0.05)]))
    cases.append(("same_success_diff_cost", [stats(True, 15, 0.01), stats(True, 15, 0.05)]))
    cases.append(("same_cost_diff_success", [stats(True, 15, 0.01), stats(False, 15, 0.01)]))
    return [{"name": n, "episodes": e} for n, e in cases]


def evaluate_all_versions(eps: Sequence[EpisodeStats]) -> Dict[str, List[float]]:
    return {
        VERSION_LEGACY_5: Legacy5Evaluator().evaluate(eps),
        VERSION_CAND_5: Candidate5Evaluator().evaluate(eps),
        VERSION_CAND_2: Candidate2Evaluator().evaluate(eps),
    }
