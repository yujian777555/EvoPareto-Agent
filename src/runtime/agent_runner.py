"""AgentRunner: uniform execution interface `agent.run(task) -> TaskResult`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from src.runtime.agent_builder import Agent
from src.runtime.result import EpisodeResult, TaskResult
from src.runtime.task import TaskSpec, TaskSuite


@dataclass
class AgentRunner:
    """Runs an Agent over one task or a suite.

    Keeps a single entrypoint so benchmarks and evaluators do not care
    whether the agent is mock-backed or LLM-backed.
    """

    default_seed: int = 0

    def run(self, agent: Agent, task: TaskSpec, *, seed: Optional[int] = None) -> TaskResult:
        s = self.default_seed if seed is None else seed
        return agent.run_task(task, seed=s)

    def run_suite(
        self,
        agent: Agent,
        suite: TaskSuite,
        *,
        seed: Optional[int] = None,
    ) -> EpisodeResult:
        s = self.default_seed if seed is None else seed
        episode = EpisodeResult(agent_id=agent.agent_id)
        for task in suite:
            episode.append(agent.run_task(task, seed=s))
        return episode


def run_agent(agent: Agent, task: TaskSpec, *, seed: int = 0) -> TaskResult:
    """Module-level convenience mirroring `agent.run(task)`."""
    return AgentRunner(default_seed=seed).run(agent, task, seed=seed)
