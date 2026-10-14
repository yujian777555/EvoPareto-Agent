"""TaskResult container (Phase 1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional


@dataclass
class TaskResult:
    """Outcome of one agent attempting one task.

    Fields are intentionally LLM-agnostic so GPT/DeepSeek runtimes can fill
    the same schema later.
    """

    task_id: str
    success: bool
    steps: int
    tokens: int
    latency: float
    cost: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.steps = int(self.steps)
        self.tokens = int(self.tokens)
        self.latency = float(self.latency)
        self.cost = float(self.cost)
        if self.steps < 0:
            raise ValueError("steps must be >= 0")
        if self.tokens < 0:
            raise ValueError("tokens must be >= 0")
        if self.latency < 0:
            raise ValueError("latency must be >= 0")
        if self.cost < 0:
            raise ValueError("cost must be >= 0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": bool(self.success),
            "steps": self.steps,
            "tokens": self.tokens,
            "latency": self.latency,
            "cost": self.cost,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskResult":
        return cls(
            task_id=str(data["task_id"]),
            success=bool(data["success"]),
            steps=int(data["steps"]),
            tokens=int(data["tokens"]),
            latency=float(data["latency"]),
            cost=float(data["cost"]),
            metadata=dict(data.get("metadata", {})),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)


@dataclass
class EpisodeResult:
    """Aggregated results of an agent over a task suite."""

    agent_id: int
    results: list = field(default_factory=list)

    def append(self, result: TaskResult) -> None:
        self.results.append(result)

    @property
    def n_tasks(self) -> int:
        return len(self.results)

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.success) / float(len(self.results))

    def totals(self) -> Dict[str, float]:
        return {
            "success_rate": self.success_rate,
            "mean_steps": _mean([r.steps for r in self.results]),
            "mean_tokens": _mean([r.tokens for r in self.results]),
            "mean_latency": _mean([r.latency for r in self.results]),
            "mean_cost": _mean([r.cost for r in self.results]),
            "n_tasks": float(self.n_tasks),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "n_tasks": self.n_tasks,
            "success_rate": self.success_rate,
            "results": [r.to_dict() for r in self.results],
            "totals": self.totals(),
        }


def _mean(values) -> float:
    if not values:
        return 0.0
    return float(sum(values)) / float(len(values))
