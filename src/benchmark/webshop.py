"""WebShop benchmark adapter (Phase 4.2).

Decision-making + cost tradeoff. Simulator by default; schema matches ALFWorld.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from src.backend.base import LLMBackend, MockLLMBackend
from src.benchmark.base_adapter import BenchmarkAdapter, episode_metrics
from src.runtime.agent_builder import Agent
from src.runtime.result import EpisodeResult, TaskResult


_SHOP_TASKS = [
    ("single_item", 0.35, ("search",), 5),
    ("attribute_match", 0.55, ("search", "click"), 8),
    ("budget_constrained", 0.70, ("search", "click", "buy"), 10),
    ("multi_item_basket", 0.85, ("search", "click", "buy", "back"), 14),
    ("substitute_choice", 0.90, ("search", "click", "buy"), 12),
]


class WebShopAdapter(BenchmarkAdapter):
    name = "webshop"

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
        self.reset()

    def reset(self) -> None:
        self._tasks = self._build_tasks()

    def _build_tasks(self) -> List[Dict[str, Any]]:
        tasks = []
        for i in range(self.n):
            kind, diff, tools, horizon = _SHOP_TASKS[i % len(_SHOP_TASKS)]
            d = min(0.98, diff * self.difficulty_scale * (0.85 + 0.3 * (i / max(1, self.n - 1))))
            tasks.append(
                {
                    "task_id": f"web-{self.seed}-{i:03d}",
                    "kind": kind,
                    "difficulty": d,
                    "required_tools": tools,
                    "horizon": horizon,
                    "goal": f"WebShop:{kind} #{i}",
                }
            )
        return tasks

    @property
    def n_tasks(self) -> int:
        return self.n

    def run(self, agent: Agent) -> EpisodeResult:
        episode = EpisodeResult(agent_id=agent.agent_id)
        for task in self._tasks:
            episode.append(self._run_one(agent, task))
        return episode

    def _run_one(self, agent: Agent, task: Dict[str, Any]) -> TaskResult:
        g = agent.genome
        prompt = (
            f"WebShop task={task['kind']} difficulty={task['difficulty']:.2f} "
            f"budget_hint={g.reasoning_budget}"
        )
        resp = self.backend.generate(prompt, budget=g.reasoning_budget)
        cap = self._capability(g, task)
        success = cap >= task["difficulty"]

        steps = max(1, int(round(task["horizon"] * (0.75 + 0.45 * (g.reasoning_budget / 128.0)))))
        if not success:
            steps = int(steps * 1.2)
        tokens = resp.tokens + steps * (8 + g.reasoning_budget // 20)
        latency = resp.latency + steps * 0.04
        # WebShop cost: tool calls dominate (buy/search).
        tool_mult = {"no_tools": 0.5, "conservative": 0.9, "balanced": 1.1, "aggressive": 1.5, "tool_first": 1.9}
        cost = resp.cost + steps * 1.5e-4 * tool_mult.get(g.tool_policy, 1.0)

        trajectory = [
            {"t": 0, "action": "search", "q": task["kind"]},
            {"t": 1, "action": f"plan:{g.planner_strategy}"},
        ]
        trajectory.append({"t": 2, "action": "buy" if success else "abandon", "success": success})

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
        planner = {"direct": 0.55, "cot": 0.70, "plan_and_solve": 0.80, "tree_search": 0.86, "reflexion": 0.84}
        memory = {"none": 0.50, "short_term": 0.62, "episodic": 0.72, "semantic": 0.78, "hybrid": 0.84}
        refl = {"none": 0.55, "self_critique": 0.68, "pairwise": 0.75, "critic_model": 0.82, "iterative": 0.86}
        tool = {"no_tools": 0.35, "conservative": 0.60, "balanced": 0.74, "aggressive": 0.84, "tool_first": 0.90}
        cap = (
            0.32 * planner.get(g.planner_strategy, 0.6)
            + 0.22 * memory.get(g.memory_strategy, 0.6)
            + 0.20 * refl.get(g.reflection_strategy, 0.6)
            + 0.26 * tool.get(g.tool_policy, 0.6)
        )
        cap += 0.10 * math.sqrt((g.reasoning_budget - 8) / 120.0)
        if task["kind"] in ("budget_constrained", "substitute_choice") and g.tool_policy in ("balanced", "conservative"):
            cap += 0.05
        if task["required_tools"] and g.tool_policy == "no_tools":
            cap -= 0.18
        h = hash((task["task_id"], g.key())) & 0xFFFF
        cap += (h / 65535.0 - 0.5) * 0.06
        return max(0.0, min(1.0, cap))

    def evaluate(self, episode: EpisodeResult) -> Dict[str, float]:
        return episode_metrics(episode)


class RealWebShopAdapter(WebShopAdapter):
    name = "webshop_real"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        try:
            import webshop  # noqa: F401

            self.available = True
        except Exception:
            self.available = False
