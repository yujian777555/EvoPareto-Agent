"""BenchmarkAdapter interface (Phase 4.2).

    adapter.reset()
    episode = adapter.run(agent)
    metrics  = adapter.evaluate(episode)

Real ALFWorld / WebShop packages are used when installed; otherwise a
deterministic **simulated** environment with the same task schema runs so the
evolution pipeline can be validated offline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.runtime.agent_builder import Agent
from src.runtime.result import EpisodeResult, TaskResult


@dataclass
class EpisodeRecord:
    """One episode on one task (Phase 4.3 schema)."""

    task_id: str
    agent_genome: Dict[str, Any]
    success: bool
    steps: int
    tokens: int
    latency: float
    cost: float
    trajectory: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "agent_genome": dict(self.agent_genome),
            "success": bool(self.success),
            "steps": int(self.steps),
            "tokens": int(self.tokens),
            "latency": float(self.latency),
            "cost": float(self.cost),
            "trajectory": list(self.trajectory),
            "metadata": dict(self.metadata),
        }


class BenchmarkAdapter(ABC):
    """Unified real/simulated benchmark interface."""

    name: str = "base"

    @abstractmethod
    def reset(self) -> None:
        """Reset episode index / environment state."""

    @abstractmethod
    def run(self, agent: Agent) -> EpisodeResult:
        """Run the full suite for `agent` and return TaskResults."""

    @abstractmethod
    def evaluate(self, episode: EpisodeResult) -> Dict[str, float]:
        """Aggregate metrics from an episode."""

    @property
    @abstractmethod
    def n_tasks(self) -> int: ...

    def run_recorded(self, agent: Agent) -> Tuple[EpisodeResult, List[EpisodeRecord]]:
        """Run and also return per-task EpisodeRecords (trajectory logging)."""
        episode = self.run(agent)
        records = []
        for r in episode.results:
            records.append(
                EpisodeRecord(
                    task_id=r.task_id,
                    agent_genome=agent.genome.to_dict(),
                    success=r.success,
                    steps=r.steps,
                    tokens=r.tokens,
                    latency=r.latency,
                    cost=r.cost,
                    trajectory=list(r.metadata.get("trajectory", [])),
                    metadata={k: v for k, v in r.metadata.items() if k != "trajectory"},
                )
            )
        return episode, records


def episode_metrics(episode: EpisodeResult) -> Dict[str, float]:
    """Shared objective-facing aggregates."""
    t = episode.totals()
    return {
        "success_rate": float(t["success_rate"]),
        "mean_steps": float(t["mean_steps"]),
        "mean_tokens": float(t["mean_tokens"]),
        "mean_latency": float(t["mean_latency"]),
        "mean_cost": float(t["mean_cost"]),
        "n_tasks": float(t["n_tasks"]),
    }
