"""MockBenchmark: synthetic tasks proving the evolution pipeline.

Different AgentGenomes produce different TaskResult profiles (success,
steps, tokens, latency, cost) via the builder's behavioral model.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from src.benchmark.base import Benchmark
from src.runtime.agent_builder import Agent
from src.runtime.agent_runner import AgentRunner
from src.runtime.result import EpisodeResult
from src.runtime.task import TaskSpec, TaskSuite


def default_mock_suite(n_tasks: int = 12) -> TaskSuite:
    """Deterministic mixed-difficulty suite."""
    if n_tasks < 1:
        raise ValueError("n_tasks must be >= 1")
    tasks = []
    for i in range(n_tasks):
        difficulty = 0.25 + 0.65 * (i / max(1, n_tasks - 1))
        tools: Tuple[str, ...]
        if i % 3 == 0:
            tools = ()
        elif i % 3 == 1:
            tools = ("search",)
        else:
            tools = ("search", "calculator", "browser")
        tasks.append(
            TaskSpec(
                task_id=f"mock-{i:03d}",
                goal=f"Mock task {i} (difficulty={difficulty:.2f})",
                difficulty=round(difficulty, 3),
                required_tools=tools,
                domain="mock",
            )
        )
    return TaskSuite(name=f"mock-suite-{n_tasks}", tasks=tuple(tasks))


class MockBenchmark(Benchmark):
    """Benchmark adapter used to validate the evolution pipeline."""

    name = "mock"

    def __init__(
        self,
        suite: Optional[TaskSuite] = None,
        *,
        n_tasks: int = 12,
        seed: int = 0,
    ) -> None:
        self.suite = suite if suite is not None else default_mock_suite(n_tasks)
        self.seed = seed
        self.runner = AgentRunner(default_seed=seed)

    def evaluate(self, agent: Agent) -> EpisodeResult:
        return self.runner.run_suite(agent, self.suite, seed=self.seed)

    @property
    def n_tasks(self) -> int:
        return len(self.suite)

    def describe(self) -> str:
        return f"MockBenchmark(n_tasks={self.n_tasks}, seed={self.seed})"
