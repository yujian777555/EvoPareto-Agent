"""Intervention credit: paired parent/child outcome difference (Stage 2.0).

Δ = R(child) − R(parent) under matched evaluation. This is a *paired
contrast estimate*, not a strict causal effect (no full randomization of
the environment). Documented as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class InterventionRecord:
    failure_context: str
    operator: str
    parent_reward: float
    child_reward: float
    task_id: str = ""

    @property
    def delta(self) -> float:
        return self.child_reward - self.parent_reward


@dataclass
class InterventionCredit:
    """Decay-updated credit of operators conditioned on failure context."""

    decay: float = 0.4
    prior: float = 0.0
    prior_weight: float = 1.0
    _sum: Dict[str, float] = field(default_factory=dict)
    _count: Dict[str, int] = field(default_factory=dict)
    _wsum: Dict[str, float] = field(default_factory=dict)  # decayed weight
    history: List[InterventionRecord] = field(default_factory=list)

    def _key(self, ctx: str, op: str) -> str:
        return f"{ctx}||{op}"

    def update(self, rec: InterventionRecord) -> None:
        k = self._key(rec.failure_context, rec.operator)
        self.history.append(rec)
        prev_w = self._wsum.get(k, self.prior_weight)
        w = self.decay * 1.0 + (1.0 - self.decay) * prev_w
        prev_s = self._sum.get(k, self.prior * self.prior_weight)
        s = self.decay * rec.delta + (1.0 - self.decay) * prev_s
        self._wsum[k] = w
        self._sum[k] = s
        self._count[k] = self._count.get(k, 0) + 1

    def mean_credit(self, ctx: str, op: str) -> float:
        k = self._key(ctx, op)
        if k not in self._sum:
            return self.prior
        w = self._wsum[k] or 1.0
        return self._sum[k] / w

    def n(self, ctx: str, op: str) -> int:
        return self._count.get(self._key(ctx, op), 0)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for k in self._sum:
            ctx, op = k.split("||", 1)
            out.setdefault(ctx, {})[op] = self.mean_credit(ctx, op)
        return out
