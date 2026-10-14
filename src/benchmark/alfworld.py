"""ALFWorld benchmark adapter (Phase 4.2).

Priority-1 real agent benchmark: planning, tool interaction, long horizon.

If the `alfworld` package is installed, `RealALFWorldAdapter` can be wired to
it. The default `ALFWorldAdapter` uses a deterministic **simulator** with the
same episode schema so PEEM-PPEC can be validated offline (no API, no download).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.backend.base import LLMBackend, MockLLMBackend
from src.benchmark.base_adapter import BenchmarkAdapter, episode_metrics
from src.runtime.agent_builder import Agent
from src.runtime.result import EpisodeResult, TaskResult


# Task catalog: goal types with difficulty / tool needs (ALFWorld-like).
_ALFTASKS = [
    ("pick_and_place", 0.45, ("put", "go"), 6),
    ("look_at_obj", 0.30, ("look", "go"), 4),
    ("pick_clean_then_place", 0.70, ("clean", "put", "go"), 10),
    ("heat_then_place", 0.75, ("heat", "put", "go"), 12),
    ("cool_then_place", 0.75, ("cool", "put", "go"), 12),
    ("two_obj_compose", 0.90, ("put", "go", "look"), 16),
]


class ALFWorldAdapter(BenchmarkAdapter):
    """ALFWorld-style task suite (simulator by default)."""

    name = "alfworld"

    def __init__(
        self,
        *,
        n_tasks: int = 12,
        seed: int = 0,
        backend: Optional[LLMBackend] = None,
        difficulty_scale: float = 1.0,
    ) -> None:
        self.n = int(n_tasks)
        self.seed = int(seed)
        self.backend = backend or MockLLMBackend()
        self.difficulty_scale = float(difficulty_scale)
        self._episodes_run = 0
        self.reset()

    def reset(self) -> None:
        self._episodes_run = 0
        self._tasks = self._build_tasks()

    def _build_tasks(self) -> List[Dict[str, Any]]:
        tasks = []
        for i in range(self.n):
            kind, diff, tools, horizon = _ALFTASKS[i % len(_ALFTASKS)]
            # Spread difficulty across the suite.
            d = min(0.98, diff * self.difficulty_scale * (0.85 + 0.3 * (i / max(1, self.n - 1))))
            tasks.append(
                {
                    "task_id": f"alf-{self.seed}-{i:03d}",
                    "kind": kind,
                    "difficulty": d,
                    "required_tools": tools,
                    "horizon": horizon,
                    "goal": f"ALFWorld:{kind} #{i}",
                }
            )
        return tasks

    @property
    def n_tasks(self) -> int:
        return self.n

    # ------------------------------------------------------------------ #
    def run(self, agent: Agent) -> EpisodeResult:
        episode = EpisodeResult(agent_id=agent.agent_id)
        for task in self._tasks:
            episode.append(self._run_one(agent, task))
        return episode

    def _run_one(self, agent: Agent, task: Dict[str, Any]) -> TaskResult:
        g = agent.genome
        # LLM call (mock or real) — costs tracked through the backend response.
        prompt = (
            f"ALFWorld task={task['kind']} difficulty={task['difficulty']:.2f}\n"
            f"Planner={g.planner_strategy} Memory={g.memory_strategy} "
            f"Reflection={g.reflection_strategy} Tools={g.tool_policy} Budget={g.reasoning_budget}"
        )
        resp = self.backend.generate(prompt, budget=g.reasoning_budget)

        # Capability model (consistent with Phase 1 semantics).
        cap = self._capability(g, task)
        success = cap >= task["difficulty"]

        # Resource accounting combines genome profile + LLM usage.
        steps = max(1, int(round(task["horizon"] * (0.7 + 0.5 * (g.reasoning_budget / 128.0)))))
        if not success:
            steps = int(steps * 1.25)
        tokens = resp.tokens + steps * (10 + g.reasoning_budget // 16)
        latency = resp.latency + steps * (0.05 if g.tool_policy != "tool_first" else 0.08)
        cost = resp.cost + steps * 1e-4 * (1.0 + (2.0 if g.tool_policy == "tool_first" else 0.0))

        trajectory = [
            {"t": 0, "action": "observe", "obs": task["kind"]},
            {"t": 1, "action": f"plan:{g.planner_strategy}", "budget": g.reasoning_budget},
        ]
        for s in range(min(3, steps)):
            trajectory.append({"t": 2 + s, "action": f"step{s}", "tool": g.tool_policy})
        trajectory.append({"t": len(trajectory), "action": "finish", "success": success})

        return TaskResult(
            task_id=task["task_id"],
            success=success,
            steps=steps,
            tokens=int(tokens),
            latency=float(latency),
            cost=float(cost),
            metadata={
                "trajectory": trajectory,
                "kind": task["kind"],
                "difficulty": task["difficulty"],
                "capability": cap,
                "reflection": g.reflection_strategy,
                "tool_policy": g.tool_policy,
                "reasoning_budget": g.reasoning_budget,
                "backend": self.backend.name,
            },
        )

    def _capability(self, g, task: Dict[str, Any]) -> float:
        planner = {"direct": 0.50, "cot": 0.68, "plan_and_solve": 0.80, "tree_search": 0.90, "reflexion": 0.88}
        memory = {"none": 0.48, "short_term": 0.60, "episodic": 0.72, "semantic": 0.80, "hybrid": 0.88}
        refl = {"none": 0.52, "self_critique": 0.70, "pairwise": 0.78, "critic_model": 0.85, "iterative": 0.90}
        tool = {"no_tools": 0.40, "conservative": 0.62, "balanced": 0.72, "aggressive": 0.82, "tool_first": 0.88}
        cap = (
            0.35 * planner.get(g.planner_strategy, 0.6)
            + 0.25 * memory.get(g.memory_strategy, 0.6)
            + 0.25 * refl.get(g.reflection_strategy, 0.6)
            + 0.15 * tool.get(g.tool_policy, 0.6)
        )
        cap += 0.12 * math.sqrt((g.reasoning_budget - 8) / 120.0)
        # Long-horizon tasks reward memory + reflection more.
        if task["horizon"] >= 10:
            cap += 0.06 if g.memory_strategy in ("episodic", "semantic", "hybrid") else -0.02
            cap += 0.05 if g.reflection_strategy in ("iterative", "critic_model") else 0.0
        # Tool-needed tasks punish no_tools.
        if task["required_tools"] and g.tool_policy == "no_tools":
            cap -= 0.15
        # Deterministic tiny noise.
        h = hash((task["task_id"], g.key())) & 0xFFFF
        cap += (h / 65535.0 - 0.5) * 0.06
        return max(0.0, min(1.0, cap))

    def evaluate(self, episode: EpisodeResult) -> Dict[str, float]:
        return episode_metrics(episode)


class RealALFWorldAdapter(ALFWorldAdapter):
    """Placeholder for a real `alfworld` package integration.

    If `import alfworld` succeeds, subclass and override `_run_one` to call the
    actual environment. The schema (TaskResult / EpisodeRecord) stays identical.
    """

    name = "alfworld_real"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        try:
            import alfworld  # noqa: F401

            self.available = True
        except Exception:
            self.available = False
