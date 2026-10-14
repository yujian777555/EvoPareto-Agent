"""AgentBuilder: AgentGenome -> Agent instance (LLM-agnostic).

The Agent object is a *configuration carrier + runtime strategy stub*.
Phase 1 does not call commercial APIs; LLM backends plug in later via
`LLMBackend` without changing the genome or builder contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol, Sequence

from src.agent.genome import AgentGenome
from src.runtime.task import TaskSpec
from src.runtime.result import TaskResult


# ------------------------------------------------------------------ #
# Optional LLM backend (future GPT / DeepSeek integration)
# ------------------------------------------------------------------ #
class LLMBackend(Protocol):
    """Minimal interface a real LLM client must satisfy."""

    def complete(self, prompt: str, *, budget: int) -> str:  # pragma: no cover
        ...


@dataclass
class AgentConfig:
    """Resolved configuration view of a genome (extensible)."""

    planner_strategy: str
    memory_strategy: str
    reflection_strategy: str
    tool_policy: str
    reasoning_budget: int
    extras: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_genome(cls, genome: AgentGenome) -> "AgentConfig":
        return cls(
            planner_strategy=genome.planner_strategy,
            memory_strategy=genome.memory_strategy,
            reflection_strategy=genome.reflection_strategy,
            tool_policy=genome.tool_policy,
            reasoning_budget=genome.reasoning_budget,
        )


@dataclass
class Agent:
    """Runtime agent instance built from an AgentGenome.

    Keeps the five genome knobs as first-class fields and provides
    `run_task`, which is used by `AgentRunner`. The default implementation
    is a deterministic *behavioral model* (no LLM): strategy names map to
    step/token/cost profiles. A future LLM backend overrides `run_task`.
    """

    genome: AgentGenome
    config: AgentConfig
    agent_id: int = 0
    llm: Optional[LLMBackend] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Exposed genome fields (requirement: Agent object contains these).
    @property
    def planner_strategy(self) -> str:
        return self.config.planner_strategy

    @property
    def memory_strategy(self) -> str:
        return self.config.memory_strategy

    @property
    def reflection_strategy(self) -> str:
        return self.config.reflection_strategy

    @property
    def tool_policy(self) -> str:
        return self.config.tool_policy

    @property
    def reasoning_budget(self) -> int:
        return self.config.reasoning_budget

    # ------------------------------------------------------------------ #
    # Execution (default: mock behavioral model)
    # ------------------------------------------------------------------ #
    def run_task(self, task: TaskSpec, *, seed: int = 0) -> TaskResult:
        """Execute one task. LLM backends may replace this method's body."""
        if self.llm is not None:
            return self._run_with_llm(task)
        return _mock_run(self, task, seed=seed)

    def _run_with_llm(self, task: TaskSpec) -> TaskResult:  # pragma: no cover
        assert self.llm is not None
        prompt = (
            f"Goal: {task.goal}\n"
            f"Planner: {self.planner_strategy}\n"
            f"Memory: {self.memory_strategy}\n"
            f"Reflection: {self.reflection_strategy}\n"
            f"Tools: {self.tool_policy}\n"
            f"Budget: {self.reasoning_budget}\n"
        )
        text = self.llm.complete(prompt, budget=self.reasoning_budget)
        steps = max(1, self.reasoning_budget // 8)
        tokens = max(1, len(text) // 4)
        return TaskResult(
            task_id=task.task_id,
            success=True,
            steps=steps,
            tokens=tokens,
            latency=float(steps),
            cost=tokens * 1e-4,
            metadata={"backend": "llm"},
        )


class AgentBuilder:
    """Factory: AgentGenome -> Agent.

    Deterministic for a given genome + agent_id. Designed for extension:
    pass `llm=` later, or override profiles via `profiles=`.
    """

    def __init__(
        self,
        *,
        llm: Optional[LLMBackend] = None,
        profiles: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> None:
        self.llm = llm
        self.profiles = profiles

    def build(self, genome: AgentGenome, *, agent_id: int = 0) -> Agent:
        if not isinstance(genome, AgentGenome):
            raise TypeError("AgentBuilder.build expects AgentGenome")
        config = AgentConfig.from_genome(genome)
        agent = Agent(
            genome=genome.clone(),
            config=config,
            agent_id=agent_id,
            llm=self.llm,
            metadata={"built_from": genome.key()},
        )
        return agent

    def build_many(self, genomes: Sequence[AgentGenome]) -> List[Agent]:
        return [self.build(g, agent_id=i) for i, g in enumerate(genomes)]


# ------------------------------------------------------------------ #
# Mock behavioral model (no LLM) — different genomes -> different results
# ------------------------------------------------------------------ #
_PLANNER_STEPS = {
    "direct": 1.0,
    "cot": 1.6,
    "plan_and_solve": 2.1,
    "tree_search": 3.2,
    "reflexion": 2.8,
}
_PLANNER_CAP = {
    "direct": 0.55,
    "cot": 0.72,
    "plan_and_solve": 0.82,
    "tree_search": 0.90,
    "reflexion": 0.88,
}
_MEMORY_CAP = {
    "none": 0.50,
    "short_term": 0.62,
    "episodic": 0.74,
    "semantic": 0.80,
    "hybrid": 0.86,
}
_MEMORY_STEP = {
    "none": 0.95,
    "short_term": 1.05,
    "episodic": 1.15,
    "semantic": 1.25,
    "hybrid": 1.35,
}
_REFLECTION_CAP = {
    "none": 0.55,
    "self_critique": 0.70,
    "pairwise": 0.78,
    "critic_model": 0.85,
    "iterative": 0.90,
}
_REFLECTION_STEP = {
    "none": 1.0,
    "self_critique": 1.25,
    "pairwise": 1.4,
    "critic_model": 1.55,
    "iterative": 1.75,
}
_TOOL_BOOST = {
    "conservative": 0.02,
    "balanced": 0.05,
    "aggressive": 0.08,
    "tool_first": 0.10,
    "no_tools": 0.0,
}
_TOOL_COST = {
    "conservative": 1.1,
    "balanced": 1.3,
    "aggressive": 1.7,
    "tool_first": 2.1,
    "no_tools": 0.8,
}
_TOOL_STEPS = {
    "conservative": 1.1,
    "balanced": 1.2,
    "aggressive": 1.5,
    "tool_first": 1.8,
    "no_tools": 0.9,
}


def _mock_run(agent: Agent, task: TaskSpec, *, seed: int) -> TaskResult:
    g = agent.genome
    difficulty = task.difficulty

    # Capability: higher is easier to succeed.
    cap = (
        0.35 * _PLANNER_CAP[g.planner_strategy]
        + 0.25 * _MEMORY_CAP[g.memory_strategy]
        + 0.25 * _REFLECTION_CAP[g.reflection_strategy]
        + 0.15 * (1.0 + _TOOL_BOOST[g.tool_policy])
    )
    # Budget helps up to a point.
    budget_t = (g.reasoning_budget - 8) / 120.0
    cap += 0.12 * (budget_t ** 0.5)
    # Tools help when task needs them.
    if task.required_tools:
        if g.tool_policy == "no_tools":
            cap -= 0.18
        else:
            cap += 0.08 * len(task.required_tools) * (0.5 + _TOOL_BOOST[g.tool_policy])

    # Deterministic tiny noise from seed + ids (no global RNG).
    noise = _stable_noise(task.task_id, g.key(), seed)
    cap += noise

    success = cap >= difficulty

    # Resource profile.
    steps = (
        2.0
        * _PLANNER_STEPS[g.planner_strategy]
        * _MEMORY_STEP[g.memory_strategy]
        * _REFLECTION_STEP[g.reflection_strategy]
        * _TOOL_STEPS[g.tool_policy]
        * (0.6 + 0.8 * budget_t)
        * (0.7 + 0.6 * difficulty)
    )
    # Reflection iterates more when failing.
    if not success:
        steps *= 1.15

    steps_i = max(1, int(round(steps)))
    tokens = max(8, int(round(steps_i * (12 + 28 * budget_t))))
    latency = steps_i * (0.8 + 0.5 * _TOOL_STEPS[g.tool_policy])
    cost = tokens * 1e-4 * _TOOL_COST[g.tool_policy] * (0.5 + budget_t)

    # Autonomy proxy: less reflection/tool escalation -> higher autonomy score
    # is handled in objective_evaluator; runtime only reports raw resources.

    return TaskResult(
        task_id=task.task_id,
        success=success,
        steps=steps_i,
        tokens=tokens,
        latency=float(latency),
        cost=float(cost),
        metadata={
            "capability": cap,
            "difficulty": difficulty,
            "seed": seed,
            "planner": g.planner_strategy,
            "memory": g.memory_strategy,
            "reflection": g.reflection_strategy,
            "tool_policy": g.tool_policy,
            "reasoning_budget": g.reasoning_budget,
        },
    )


def _stable_noise(task_id: str, genome_key, seed: int) -> float:
    """Deterministic noise in [-0.06, 0.06]."""
    payload = f"{task_id}|{genome_key}|{seed}".encode("utf-8")
    h = 0
    for b in payload:
        h = (h * 131 + b) & 0xFFFFFFFF
    u = (h % 10000) / 10000.0
    return (u - 0.5) * 0.12
