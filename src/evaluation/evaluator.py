"""Toy evaluation environment for Phase 0.

Maps an AgentGenome to a deterministic 5-objective vector without calling any
real LLM. The mapping is intentionally smooth-with-tradeoffs so that a real
Pareto front emerges and NSGA-III can be verified.

Objectives (raw / paper semantics, higher-better except cost):
    performance, efficiency, cost, robustness, autonomy
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from src.agent.genome import (
    MAX_BUDGET,
    MEMORY_STRATEGIES,
    MIN_BUDGET,
    PLANNER_STRATEGIES,
    REFLECTION_STRATEGIES,
    TOOL_POLICIES,
    AgentGenome,
)
from src.evaluation.objectives import N_OBJECTIVES, to_minimization


# Categorical contribution tables (designed tradeoffs).
# planner: stronger planners improve performance but cost more / less efficient.
_PLANNER = {
    "direct":         {"performance": 0.35, "efficiency": 0.95, "cost": 0.15, "robustness": 0.30, "autonomy": 0.40},
    "cot":            {"performance": 0.60, "efficiency": 0.70, "cost": 0.35, "robustness": 0.50, "autonomy": 0.55},
    "plan_and_solve": {"performance": 0.75, "efficiency": 0.55, "cost": 0.55, "robustness": 0.70, "autonomy": 0.70},
    "tree_search":    {"performance": 0.90, "efficiency": 0.35, "cost": 0.85, "robustness": 0.80, "autonomy": 0.85},
    "reflexion":      {"performance": 0.85, "efficiency": 0.45, "cost": 0.70, "robustness": 0.90, "autonomy": 0.75},
}

_MEMORY = {
    "none":       {"performance": 0.40, "efficiency": 0.90, "cost": 0.10, "robustness": 0.35, "autonomy": 0.30},
    "short_term": {"performance": 0.55, "efficiency": 0.75, "cost": 0.25, "robustness": 0.50, "autonomy": 0.45},
    "episodic":   {"performance": 0.70, "efficiency": 0.60, "cost": 0.45, "robustness": 0.65, "autonomy": 0.60},
    "semantic":   {"performance": 0.75, "efficiency": 0.55, "cost": 0.55, "robustness": 0.70, "autonomy": 0.70},
    "hybrid":     {"performance": 0.85, "efficiency": 0.45, "cost": 0.70, "robustness": 0.85, "autonomy": 0.80},
}

_REFLECTION = {
    "none":           {"performance": 0.45, "efficiency": 0.90, "cost": 0.10, "robustness": 0.35, "autonomy": 0.35},
    "self_critique":  {"performance": 0.65, "efficiency": 0.70, "cost": 0.35, "robustness": 0.60, "autonomy": 0.55},
    "pairwise":       {"performance": 0.75, "efficiency": 0.55, "cost": 0.55, "robustness": 0.70, "autonomy": 0.65},
    "critic_model":   {"performance": 0.85, "efficiency": 0.45, "cost": 0.75, "robustness": 0.80, "autonomy": 0.70},
    "iterative":      {"performance": 0.90, "efficiency": 0.35, "cost": 0.85, "robustness": 0.85, "autonomy": 0.85},
}

_TOOL = {
    "conservative": {"performance": 0.55, "efficiency": 0.70, "cost": 0.30, "robustness": 0.75, "autonomy": 0.50},
    "balanced":     {"performance": 0.70, "efficiency": 0.65, "cost": 0.45, "robustness": 0.70, "autonomy": 0.65},
    "aggressive":   {"performance": 0.85, "efficiency": 0.50, "cost": 0.70, "robustness": 0.55, "autonomy": 0.80},
    "tool_first":   {"performance": 0.90, "efficiency": 0.40, "cost": 0.85, "robustness": 0.50, "autonomy": 0.90},
    "no_tools":     {"performance": 0.35, "efficiency": 0.95, "cost": 0.10, "robustness": 0.40, "autonomy": 0.25},
}

_OBJ_KEYS = ("performance", "efficiency", "cost", "robustness", "autonomy")


def _noise(genome: AgentGenome, objective: str) -> float:
    """Deterministic tiny hash noise in [-0.02, 0.02] so equal configs match."""
    payload = f"{genome.to_json()}|{objective}".encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    # Map first 8 hex chars to [0, 1), then to [-0.02, 0.02]
    u = int(digest[:8], 16) / 0xFFFFFFFF
    return (u - 0.5) * 0.04


def _budget_effects(budget: int) -> Dict[str, float]:
    """Normalized budget in (0, 1] with diminishing returns."""
    t = (budget - MIN_BUDGET) / float(MAX_BUDGET - MIN_BUDGET)  # 0..1
    # Diminishing returns on performance/robustness; near-linear cost.
    return {
        "performance": 0.15 * math.sqrt(t),
        "efficiency": -0.25 * t,          # higher budget hurts efficiency
        "cost": 0.45 * t,                  # higher budget raises cost
        "robustness": 0.12 * math.sqrt(t),
        "autonomy": 0.10 * t,
    }


def _interaction(genome: AgentGenome) -> Dict[str, float]:
    """Small pairwise interaction terms to create a non-trivial front shape."""
    out = {k: 0.0 for k in _OBJ_KEYS}
    # tree_search + no_tools is a bad combo (performance drops).
    if genome.planner_strategy == "tree_search" and genome.tool_policy == "no_tools":
        out["performance"] -= 0.12
        out["efficiency"] -= 0.05
    # hybrid memory + iterative reflection: synergy on robustness/autonomy.
    if genome.memory_strategy == "hybrid" and genome.reflection_strategy == "iterative":
        out["robustness"] += 0.08
        out["autonomy"] += 0.06
        out["cost"] += 0.08
    # direct + no_tools + low budget: very cheap, very weak.
    if (
        genome.planner_strategy == "direct"
        and genome.tool_policy == "no_tools"
        and genome.reasoning_budget <= 24
    ):
        out["cost"] -= 0.08
        out["performance"] -= 0.05
        out["efficiency"] += 0.05
    return out


@dataclass
class ToyEvaluator:
    """Deterministic multi-objective evaluator for Algorithm validation."""

    noise_scale: float = 1.0  # set 0 for fully smooth landscape
    clip_low: float = 0.0
    clip_high: float = 1.0

    def __call__(self, genome: AgentGenome) -> List[float]:
        return self.evaluate(genome)

    def evaluate(self, genome: AgentGenome) -> List[float]:
        if not isinstance(genome, AgentGenome):
            raise TypeError("ToyEvaluator expects AgentGenome")

        acc = {k: 0.0 for k in _OBJ_KEYS}
        tables = (
            (_PLANNER, genome.planner_strategy),
            (_MEMORY, genome.memory_strategy),
            (_REFLECTION, genome.reflection_strategy),
            (_TOOL, genome.tool_policy),
        )
        for table, key in tables:
            row = table[key]
            for k in _OBJ_KEYS:
                acc[k] += row[k]

        # Average categorical contributions (each in ~[0,1] after /4).
        for k in _OBJ_KEYS:
            acc[k] /= 4.0

        # Budget effects.
        for k, delta in _budget_effects(genome.reasoning_budget).items():
            acc[k] += delta

        # Interaction terms.
        for k, delta in _interaction(genome).items():
            acc[k] += delta

        # Deterministic noise.
        if self.noise_scale:
            for k in _OBJ_KEYS:
                acc[k] += self.noise_scale * _noise(genome, k)

        raw = [acc[k] for k in _OBJ_KEYS]
        raw = [min(self.clip_high, max(self.clip_low, v)) for v in raw]
        return raw

    def evaluate_min(self, genome: AgentGenome) -> List[float]:
        return to_minimization(self.evaluate(genome))
