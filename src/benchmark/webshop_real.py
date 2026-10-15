"""WebShop real-LLM adapter (Phase 5-Benchmark Extension).

Same `BenchmarkAdapter` contract as ALFWorldRealAdapter:

    reset() / run(agent) / evaluate(episode)

Focus: **cost-performance tradeoff** (search/click/buy actions, token & step cost).
Episode schema is identical to ALFWorld (`task_id, genome, success, steps,
tokens, latency, cost, trajectory`).
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from src.backend.base import DeepSeekBackend, LLMBackend, MockLLMBackend, get_env_key
from src.benchmark.base_adapter import BenchmarkAdapter, episode_metrics
from src.runtime.agent_builder import Agent
from src.runtime.cache import CacheEntry, EvaluationCache, genome_hash, make_key
from src.runtime.result import EpisodeResult, TaskResult


_SHOP_TEMPLATES = [
    {
        "task_id": "buy_blue_mug",
        "goal": "buy a blue ceramic mug under $15",
        "hint": "search blue ceramic mug, filter price under 15, click item, buy now",
        "difficulty": 0.50,
        "horizon": 6,
    },
    {
        "task_id": "headphones_budget",
        "goal": "buy wireless headphones with noise cancelling under $80",
        "hint": "search wireless headphones noise cancelling, sort price, click, buy",
        "difficulty": 0.65,
        "horizon": 8,
    },
    {
        "task_id": "two_items_basket",
        "goal": "add a desk lamp and a notebook to cart and checkout",
        "hint": "search desk lamp, click add cart, search notebook, click add cart, buy",
        "difficulty": 0.78,
        "horizon": 12,
    },
    {
        "task_id": "substitute_shoes",
        "goal": "find running shoes size 10 and pick the cheapest in-stock option",
        "hint": "search running shoes size 10, filter in stock, sort price low to high, buy",
        "difficulty": 0.72,
        "horizon": 9,
    },
    {
        "task_id": "gift_under_30",
        "goal": "buy a gift item rated 4+ stars under $30",
        "hint": "search gift, filter rating 4+, filter price under 30, click, buy",
        "difficulty": 0.60,
        "horizon": 7,
    },
]


class WebShopRealAdapter(BenchmarkAdapter):
    """WebShop adapter with LLM backend + evaluation cache."""

    name = "webshop_real"

    def __init__(
        self,
        *,
        n_tasks: int = 20,
        seed: int = 0,
        backend: Optional[LLMBackend] = None,
        cache: Optional[EvaluationCache] = None,
        use_fallback_on_error: bool = True,
        max_workers: int = 4,
    ) -> None:
        self.n = int(n_tasks)
        self.seed = int(seed)
        self.use_fallback_on_error = use_fallback_on_error
        self.max_workers = max(1, int(max_workers))
        self.cache = cache if cache is not None else EvaluationCache()
        self.backend = backend or self._default_backend()
        self.api_calls = 0
        self.cache_used = 0
        self.reset()

    @staticmethod
    def _default_backend() -> LLMBackend:
        if get_env_key("DEEPSEEK_API_KEY"):
            return DeepSeekBackend()
        if get_env_key("OPENAI_API_KEY"):
            from src.backend.base import OpenAIBackend

            return OpenAIBackend()
        return MockLLMBackend()

    def reset(self) -> None:
        self._tasks = self._build_tasks()
        self.api_calls = 0
        self.cache_used = 0

    def _build_tasks(self) -> List[Dict[str, Any]]:
        tasks = []
        for i in range(self.n):
            tpl = _SHOP_TEMPLATES[i % len(_SHOP_TEMPLATES)]
            tasks.append({**tpl, "task_id": f"{tpl['task_id']}-{self.seed}-{i:03d}"})
        return tasks

    @property
    def n_tasks(self) -> int:
        return self.n

    def run(self, agent: Agent) -> EpisodeResult:
        episode = EpisodeResult(agent_id=agent.agent_id)
        if self.max_workers <= 1:
            for task in self._tasks:
                episode.append(self._run_one(agent, task))
            return episode
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: Dict[str, TaskResult] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            futs = {pool.submit(self._run_one, agent, t): t["task_id"] for t in self._tasks}
            for fut in as_completed(futs):
                results[futs[fut]] = fut.result()
        for t in self._tasks:
            episode.append(results[t["task_id"]])
        return episode

    def _run_one(self, agent: Agent, task: Dict[str, Any]) -> TaskResult:
        g = agent.genome
        key = make_key(
            g, task_id=task["task_id"], benchmark=self.name, seed=self.seed,
            backend=getattr(self.backend, "name", ""),
            model=getattr(self.backend, "model", ""),
        )
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_used += 1
            meta = dict(cached.extra)
            meta.update({"cached": True, "api_status": meta.get("api_status", "cached")})
            if "trajectory" not in meta:
                meta["trajectory"] = []
            return TaskResult(
                task_id=task["task_id"],
                success=cached.success,
                steps=cached.steps,
                tokens=cached.tokens,
                latency=cached.latency,
                cost=cached.cost,
                metadata=meta,
            )

        prompt = self._build_prompt(task, g)
        api_status = "ok"
        try:
            resp = self.backend.generate(prompt, budget=g.reasoning_budget)
            self.api_calls += 1
        except Exception as e:
            # P0: NEVER silently replace real LLM with Mock.
            self.api_calls += 1
            api_status = f"error:{type(e).__name__}"
            return TaskResult(
                task_id=task["task_id"],
                success=False,
                steps=0,
                tokens=0,
                latency=0.0,
                cost=0.0,
                metadata={
                    "api_status": api_status,
                    "api_error": str(e)[:300],
                    "backend": self.backend.name,
                    "model": getattr(self.backend, "model", "unknown"),
                    "cached": False,
                    "trajectory": [],
                    "evaluation_kind": "real_llm_failed",
                },
            )

        success, score = self._score_completion(resp.text, task, g)
        steps = max(1, int(round(task["horizon"] * (0.7 + 0.4 * (g.reasoning_budget / 128.0)))))
        if not success:
            steps = int(steps * 1.2)
        tokens = resp.tokens + steps * 5
        tool_mult = {"no_tools": 0.5, "conservative": 0.9, "balanced": 1.1, "aggressive": 1.5, "tool_first": 1.9}
        latency = resp.latency + steps * 0.03
        cost = resp.cost + steps * 1.5e-4 * tool_mult.get(g.tool_policy, 1.0)

        trajectory = [
            {"t": 0, "action": "search", "q": task["goal"][:40]},
            {"t": 1, "action": f"plan:{g.planner_strategy}"},
            {"t": 2, "action": "buy" if success else "abandon", "success": success},
        ]
        extra = {
            "trajectory": trajectory,
            "goal": task["goal"],
            "difficulty": task["difficulty"],
            "score": score,
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", "unknown"),
            "api_status": api_status,
            "cached": False,
            "evaluation_kind": "real_llm_proxy",
            "reflection": g.reflection_strategy,
            "tool_policy": g.tool_policy,
            "reasoning_budget": g.reasoning_budget,
        }
        self.cache.store_genome_task(
            g, task["task_id"],
            CacheEntry(genome_hash(g), task["task_id"], [], int(tokens), float(cost),
                       float(latency), success, steps, extra),
            benchmark=self.name, seed=self.seed,
            backend=getattr(self.backend, "name", ""),
            model=getattr(self.backend, "model", ""),
        )
        return TaskResult(
            task_id=task["task_id"], success=success, steps=steps,
            tokens=int(tokens), latency=float(latency), cost=float(cost),
            metadata=extra,
        )

    def _build_prompt(self, task: Dict[str, Any], g) -> str:
        return (
            "You are a WebShop shopping agent.\n"
            f"Task: {task['goal']}\n"
            f"Planner: {g.planner_strategy}\n"
            f"Memory: {g.memory_strategy}\n"
            f"Reflection: {g.reflection_strategy}\n"
            f"Tool policy: {g.tool_policy}\n"
            f"Reasoning budget: {g.reasoning_budget}\n"
            "Reply with search → filter → click → buy steps, then FINISH."
        )

    def _score_completion(self, text: str, task: Dict[str, Any], g) -> Tuple[bool, float]:
        """SYNTHETIC / PROXY scoring — not native WebShop evaluation.

        Uses genome capability prior + LLM text signals. Labeled
        `evaluation_kind=real_llm_proxy`. Do not cite as real-environment success.
        """
        low = (text or "").lower()
        hint_words = [w for w in task["hint"].lower().split() if len(w) > 3]
        covered = sum(1 for w in hint_words if w in low)
        coverage = covered / max(1, len(hint_words))
        has_finish = "finish" in low
        has_buy = "buy" in low
        quality = 0.45 * coverage + 0.25 * float(has_finish) + 0.30 * float(has_buy)
        cap = (
            0.30 * {"direct": 0.50, "cot": 0.68, "plan_and_solve": 0.80, "tree_search": 0.86, "reflexion": 0.84}.get(g.planner_strategy, 0.6)
            + 0.22 * {"none": 0.48, "short_term": 0.62, "episodic": 0.72, "semantic": 0.78, "hybrid": 0.84}.get(g.memory_strategy, 0.6)
            + 0.20 * {"none": 0.52, "self_critique": 0.70, "pairwise": 0.76, "critic_model": 0.82, "iterative": 0.86}.get(g.reflection_strategy, 0.6)
            + 0.28 * {"no_tools": 0.38, "conservative": 0.60, "balanced": 0.74, "aggressive": 0.84, "tool_first": 0.88}.get(g.tool_policy, 0.6)
        )
        cap += 0.10 * math.sqrt(max(0.0, (g.reasoning_budget - 8) / 120.0))
        if task.get("difficulty", 0.5) >= 0.7 and g.tool_policy in ("balanced", "tool_first", "aggressive"):
            cap += 0.04
        score = 0.75 * cap + 0.25 * quality
        return score >= task["difficulty"], float(min(1.0, max(0.0, score)))

    def evaluate(self, episode: EpisodeResult) -> Dict[str, float]:
        m = episode_metrics(episode)
        m["api_calls"] = float(self.api_calls)
        m["cache_used"] = float(self.cache_used)
        return m

    def cost_report(self) -> Dict[str, Any]:
        usage = self.backend.usage() if hasattr(self.backend, "usage") else {}
        return {
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", "unknown"),
            "api_calls": self.api_calls,
            "cache_used": self.cache_used,
            "cache_stats": self.cache.stats(),
            "llm_usage": usage,
        }
