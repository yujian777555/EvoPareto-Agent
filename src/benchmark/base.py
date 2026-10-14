"""Benchmark abstract interface (Phase 1)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List

from src.runtime.result import EpisodeResult, TaskResult

if TYPE_CHECKING:  # pragma: no cover
    from src.runtime.agent_builder import Agent


class Benchmark(ABC):
    """Contract: evaluate an agent and return structured task results.

    `evaluate(agent)` is the required entrypoint from the Phase 1 spec.
    Concrete benchmarks own their task suite and scoring metadata.
    """

    name: str = "base"

    @abstractmethod
    def evaluate(self, agent: "Agent") -> EpisodeResult:
        """Run the benchmark for `agent` and return episode-level results."""

    @property
    @abstractmethod
    def n_tasks(self) -> int:
        ...

    def describe(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, n_tasks={self.n_tasks})"
