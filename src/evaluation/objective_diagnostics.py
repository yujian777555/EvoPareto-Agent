"""Objective validity diagnostics (Phase5-R3-R4 Task4) — audit only.

Does NOT replace paper objectives. Produces counterexamples and candidate
formulas for Planner review.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence


def efficiency_v1(steps: int, tokens: int, max_steps: int = 20) -> float:
    """Current native efficiency (higher better)."""
    return 1.0 / (1.0 + steps / max(1, max_steps) + tokens / 2000.0)


def quick_fail_beats_try(success: bool, steps: int, tokens: int, max_steps: int = 20) -> bool:
    """True if a quick fail scores higher efficiency than a longer attempt."""
    fail_fast = efficiency_v1(1, 20, max_steps)
    try_long = efficiency_v1(steps, tokens, max_steps)
    return (not success) and fail_fast > try_long


def efficiency_counterexamples(max_steps: int = 20) -> Dict[str, Any]:
    return {
        "quick_fail_1step": efficiency_v1(1, 20, max_steps),
        "serious_fail_10step": efficiency_v1(10, 400, max_steps),
        "success_12step": efficiency_v1(12, 500, max_steps),
        "quick_fail_beats_serious_try": quick_fail_beats_try(False, 10, 400, max_steps),
        "quick_fail_beats_success": (not True) and False or (
            efficiency_v1(1, 20, max_steps) > efficiency_v1(12, 500, max_steps)
        ),
    }


def efficiency_conditional_candidate(
    success: bool, steps: int, tokens: int, max_steps: int = 20
) -> float:
    """Candidate (NOT approved): success-conditioned resource efficiency.

    Failed episodes get a penalty term so quick-fail cannot dominate.
    """
    base = efficiency_v1(steps, tokens, max_steps)
    return base if success else 0.35 * base


def robustness_redundancy(perf: float, stall: float) -> Dict[str, float]:
    current = perf * (1.0 - stall)
    return {
        "performance": perf,
        "stall_rate": stall,
        "robustness_current": current,
        "identical_when_perf_zero": current == 0.0,
    }


def autonomy_from_behavior(
    n_steps: int,
    n_fallbacks: int,
    n_external_help: int = 0,
) -> float:
    """Candidate autonomy: 1 - fallback_rate - external_help_rate (0..1)."""
    if n_steps <= 0:
        return 0.0
    return max(0.0, 1.0 - n_fallbacks / n_steps - 0.5 * n_external_help / n_steps)


def cost_resolution(raw_costs: Sequence[float]) -> Dict[str, float]:
    if not raw_costs:
        return {"min": 0.0, "max": 0.0, "range": 0.0, "saturating_range": 0.0}
    lo, hi = min(raw_costs), max(raw_costs)
    def sat(c: float) -> float:
        return c / (c + 1.0)
    return {
        "min": lo,
        "max": hi,
        "range": hi - lo,
        "saturating_range": sat(hi) - sat(lo),
    }


def full_audit_table() -> List[Dict[str, Any]]:
    return [
        {
            "objective": "performance",
            "source": "env won",
            "valid": True,
            "issues": "",
        },
        {
            "objective": "efficiency",
            "source": "steps+tokens",
            "valid": False,
            "issues": "quick-fail can beat serious try; horizon-dependent",
        },
        {
            "objective": "cost",
            "source": "API $ / saturating transform",
            "valid": True,
            "issues": "low dynamic range on micro costs; direction=min",
        },
        {
            "objective": "robustness",
            "source": "perf*(1-stall)",
            "valid": False,
            "issues": "coupled to performance; zero when all fail",
        },
        {
            "objective": "autonomy",
            "source": "early-budget/stall penalties",
            "valid": False,
            "issues": "behavioral proxy only; not independent autonomy",
        },
    ]


def plan_a_vs_plan_b() -> Dict[str, Any]:
    return {
        "plan_a_keep_5_with_protocol": {
            "pros": ["keeps paper structure", "success/cost stay native"],
            "cons": ["efficiency/robustness/autonomy need redesign", "Goodhart risk"],
            "requirements": [
                "success-conditioned efficiency",
                "independent robustness protocol (multi-instance)",
                "behavioral autonomy (fallback/help rates)",
            ],
        },
        "plan_b_reduce_reorganize": {
            "pros": ["higher construct validity", "less redundancy"],
            "cons": ["changes paper framing", "fewer axes for PPEC demo"],
            "requirements": [
                "Planner approval",
                "update PPEC preference vectors",
                "re-run baselines",
            ],
        },
    }
