"""ObjectiveEvaluator: TaskResult(s) -> paper objective vector.

Output (paper semantics, mixed max/min):

    [performance, efficiency, cost, robustness, autonomy]

maximize: performance, efficiency, robustness, autonomy
minimize: cost

Phase 0 mixed-direction conversion (`to_minimization`) is reused unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from src.evaluation.objectives import (
    MAXIMIZE,
    N_OBJECTIVES,
    OBJECTIVE_NAMES,
    to_minimization,
)
from src.runtime.result import EpisodeResult, TaskResult


@dataclass
class ObjectiveEvaluator:
    """Map episode / task outcomes to the 5-objective paper vector.

    Normalization helpers map raw resources to [0, 1] with saturating
    curves so objectives are comparable for NSGA-III niching.
    """

    ref_steps: float = 24.0
    ref_tokens: float = 800.0
    ref_latency: float = 40.0
    ref_cost: float = 0.35
    low_autonomy_reflection: Sequence[str] = ("critic_model", "pairwise")
    high_autonomy_reflection: Sequence[str] = ("none", "self_critique")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def from_episode(self, episode: EpisodeResult) -> List[float]:
        if episode.n_tasks == 0:
            raise ValueError("EpisodeResult has no tasks")
        results = episode.results
        performance = episode.success_rate
        efficiency = _mean([self._efficiency(r) for r in results])
        cost = _mean([self._cost_score(r) for r in results])  # lower better
        robustness = self._robustness(results)
        autonomy = _mean([self._autonomy(r) for r in results])
        vector = [performance, efficiency, cost, robustness, autonomy]
        return [_clip01(v) for v in vector]

    def from_results(self, results: Sequence[TaskResult]) -> List[float]:
        ep = EpisodeResult(agent_id=-1)
        for r in results:
            ep.append(r)
        return self.from_episode(ep)

    def to_minimization(self, vector: Sequence[float]) -> List[float]:
        """Phase 0 mixed-direction conversion (max except cost)."""
        return to_minimization(vector)

    def names(self) -> Sequence[str]:
        return OBJECTIVE_NAMES

    # ------------------------------------------------------------------ #
    # Components
    # ------------------------------------------------------------------ #
    def _efficiency(self, r: TaskResult) -> float:
        # Saturating inverse of resource usage (steps/tokens/latency).
        s = r.steps / self.ref_steps
        t = r.tokens / self.ref_tokens
        l = r.latency / self.ref_latency
        raw = 1.0 / (1.0 + 0.45 * s + 0.35 * t + 0.20 * l)
        # Successful cheap solves are the most efficient.
        return raw * (1.0 if r.success else 0.55)

    def _cost_score(self, r: TaskResult) -> float:
        """Monetary/token cost (lower is better), clipped to [0, 1]."""
        return r.cost / (r.cost + self.ref_cost)

    def _robustness(self, results: Sequence[TaskResult]) -> float:
        """Success consistency: high mean success and low failure clustering."""
        if not results:
            return 0.0
        mean_s = sum(1.0 for r in results if r.success) / len(results)
        # Penalize if all success is concentrated on easy tasks only.
        by_diff = sorted(results, key=lambda r: float(r.metadata.get("difficulty", 0.5)))
        k = max(1, len(by_diff) // 3)
        hard = by_diff[-k:]
        hard_s = sum(1.0 for r in hard if r.success) / len(hard)
        return 0.6 * mean_s + 0.4 * hard_s

    def _autonomy(self, r: TaskResult) -> float:
        """Less external critic / more self-driven execution => higher."""
        reflection = str(r.metadata.get("reflection", "none"))
        tool_policy = str(r.metadata.get("tool_policy", "balanced"))
        budget = int(r.metadata.get("reasoning_budget", 32))

        if reflection in self.high_autonomy_reflection:
            base = 0.78
        elif reflection in self.low_autonomy_reflection:
            base = 0.48
        else:
            base = 0.62

        # Slight penalty for aggressive external tool reliance.
        if tool_policy in ("tool_first", "aggressive"):
            base -= 0.08
        elif tool_policy == "no_tools":
            base += 0.04

        # Moderate budget => self-regulation.
        t = (budget - 8) / 120.0
        base += 0.10 * (1.0 - abs(t - 0.45) * 1.4)
        if r.success:
            base += 0.05
        return base


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))
