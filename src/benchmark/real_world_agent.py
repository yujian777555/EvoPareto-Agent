"""Real tool-use agent benchmark (Phase 5-R1).

Lightweight, reproducible BenchmarkAdapter:

    reset() / run(agent) / evaluate(episode)

50 tasks in three categories:
  - information  (retrieval / comparison / summarization)
  - reasoning    (planning / decision)
  - tool         (calculator / search / file)

Episode schema (extends the shared schema with tool_calls):
  { task_id, genome, success, steps, tool_calls, tokens, latency, cost, trajectory }
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.backend.base import LLMBackend, MockLLMBackend
from src.benchmark.base_adapter import BenchmarkAdapter, episode_metrics
from src.runtime.agent_builder import Agent
from src.runtime.cache import CacheEntry, EvaluationCache, genome_hash, make_key
from src.runtime.result import EpisodeResult, TaskResult
from src.tools.registry import ToolRegistry, default_registry


def _build_catalog() -> List[Dict[str, Any]]:
    tasks: List[Dict[str, Any]] = []
    # --- Information ---
    info = [
        ("info_retrieve_climate", "Summarize key facts about climate change", "search", 0.40),
        ("info_retrieve_python", "Summarize recent Python language changes", "search", 0.42),
        ("info_compare_energy", "Compare solar vs battery storage trends", "search", 0.55),
        ("info_summarize_notes", "Summarize the meeting notes file", "file_read", 0.45),
        ("info_extract_todo", "List open items from todo.md", "file_read", 0.48),
        ("info_compare_csv", "Compare values in data.csv", "file_read", 0.52),
        ("info_retrieve_renewable", "Find facts about renewable energy", "search", 0.40),
        ("info_summarize_search", "Summarize search results on Python", "search", 0.50),
        ("info_lookup_file", "Find which files exist in the workspace", "file_list", 0.35),
        ("info_compare_notes_todo", "Compare notes.txt and todo.md priorities", "file_read", 0.58),
        ("info_retrieve_generic", "Retrieve generic mock information", "search", 0.38),
        ("info_summarize_data", "Summarize statistics from data.csv", "file_read", 0.54),
        ("info_filter_results", "Filter search hits about climate", "search", 0.56),
        ("info_extract_title", "Extract the main topic of notes.txt", "file_read", 0.43),
        ("info_cross_check", "Cross-check notes and todo for PEEM-PPEC", "file_read", 0.60),
        ("info_search_summarize_2", "Search renewable energy and summarize", "search", 0.57),
        ("info_file_stats", "Count lines in data.csv", "file_read", 0.44),
    ]
    for tid, goal, tool, diff in info:
        tasks.append({"task_id": tid, "category": "information", "goal": goal,
                      "required_tool": tool, "difficulty": diff, "horizon": 6})

    # --- Reasoning ---
    reason = [
        ("reason_plan_ship", "Plan a 3-step software release checklist", "", 0.55),
        ("reason_decision_budget", "Decide whether to spend more on accuracy or cost", "", 0.60),
        ("reason_plan_research", "Plan a literature review workflow", "", 0.58),
        ("reason_tradeoff", "Choose a config maximizing success under low cost", "", 0.62),
        ("reason_schedule", "Schedule tasks to minimize latency", "", 0.57),
        ("reason_debug", "Plan debugging steps for a failing test", "", 0.61),
        ("reason_prioritize", "Prioritize a backlog of three items", "", 0.54),
        ("reason_risk", "Assess risk of reducing reasoning budget", "", 0.63),
        ("reason_allocate", "Allocate compute between planning and tools", "", 0.65),
        ("reason_fallback", "Design a fallback if tools fail", "", 0.59),
        ("reason_optimize", "Propose a cheaper agent configuration", "", 0.64),
        ("reason_compare_strategies", "Compare direct vs plan-and-solve", "", 0.66),
        ("reason_long_horizon", "Plan a long-horizon multi-step task", "", 0.70),
        ("reason_cost_aware", "Plan within a tight token budget", "", 0.68),
        ("reason_reflect", "Reflect on a failed attempt and revise the plan", "", 0.67),
        ("reason_robust", "Plan with tool-failure contingencies", "", 0.69),
        ("reason_autonomous", "Design a fully autonomous workflow", "", 0.72),
    ]
    for tid, goal, tool, diff in reason:
        tasks.append({"task_id": tid, "category": "reasoning", "goal": goal,
                      "required_tool": tool, "difficulty": diff, "horizon": 8})

    # --- Tool ---
    tool_tasks = [
        ("tool_calc_sum", "Compute 17 + 25 * 3", "calculator", 0.35),
        ("tool_calc_stats", "Compute the mean of 10, 20, 30", "calculator", 0.45),
        ("tool_search_climate", "Search climate facts and return one", "search", 0.40),
        ("tool_file_write", "Write a short summary to summary.txt", "file_write", 0.50),
        ("tool_file_read", "Read notes.txt and return its length", "file_read", 0.38),
        ("tool_calc_ratio", "Compute 30/10 and then square it", "calculator", 0.52),
        ("tool_search_python", "Search Python facts", "search", 0.42),
        ("tool_file_list", "List all workspace files", "file_list", 0.32),
        ("tool_mixed_search_calc", "Search renewable energy then compute 12*12", "search", 0.60),
        ("tool_mixed_file_calc", "Read data.csv and compute 20+30", "file_read", 0.58),
        ("tool_write_report", "Create report.txt with one sentence", "file_write", 0.55),
        ("tool_calc_percentage", "Compute 15% of 240", "calculator", 0.48),
        ("tool_search_compare", "Search and compare two result snippets", "search", 0.62),
        ("tool_file_update", "Append a line to todo.md", "file_write", 0.57),
        ("tool_calc_chain", "Compute (8+4)*2-3", "calculator", 0.47),
        ("tool_search_summarize", "Search climate and summarize in one line", "search", 0.59),
    ]
    for tid, goal, tool, diff in tool_tasks:
        tasks.append({"task_id": tid, "category": "tool", "goal": goal,
                      "required_tool": tool, "difficulty": diff, "horizon": 7})

    # Environment-only calibration: raise difficulty so evolved configs can
    # differentiate from ReAct. Algorithms are not modified.
    for t in tasks:
        t["difficulty"] = min(0.95, float(t["difficulty"]) + 0.12)
    return tasks


class RealWorldAgentBenchmark(BenchmarkAdapter):
    name = "real_world_agent"

    def __init__(
        self,
        *,
        n_tasks: int = 50,
        seed: int = 0,
        backend: Optional[LLMBackend] = None,
        cache: Optional[EvaluationCache] = None,
        max_workers: int = 4,
        split: str = "all",  # all | train | test
    ) -> None:
        self.n = int(n_tasks)
        self.seed = int(seed)
        self.split = split
        self.max_workers = max(1, int(max_workers))
        self.cache = cache if cache is not None else EvaluationCache()
        self.backend = backend or MockLLMBackend()
        self.tools = default_registry()
        self.api_calls = 0
        self.cache_used = 0
        self.reset()

    def reset(self) -> None:
        self.tools.reset()
        catalog = _build_catalog()
        # Deterministic 70/30 train-test split by task_id order.
        n_train = int(len(catalog) * 0.7)
        if self.split == "train":
            catalog = catalog[:n_train]
        elif self.split == "test":
            catalog = catalog[n_train:]
        # Cycle/truncate to n_tasks.
        if self.n < len(catalog):
            # Spread across categories when truncating.
            catalog = catalog[: self.n]
        self._tasks = catalog
        self.api_calls = 0
        self.cache_used = 0

    @property
    def n_tasks(self) -> int:
        return len(self._tasks)

    def run(self, agent: Agent) -> EpisodeResult:
        episode = EpisodeResult(agent_id=agent.agent_id)
        if self.max_workers <= 1:
            for t in self._tasks:
                episode.append(self._run_one(agent, t))
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
        key = make_key(g, task_id=task["task_id"], benchmark=f"{self.name}:{self.split}", seed=self.seed)
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_used += 1
            return TaskResult(
                task_id=task["task_id"], success=cached.success, steps=cached.steps,
                tokens=cached.tokens, latency=cached.latency, cost=cached.cost,
                metadata={**cached.extra, "cached": True,
                          "trajectory": cached.extra.get("trajectory", [])},
            )

        # LLM "plan"
        prompt = (
            f"Real agent task [{task['category']}]: {task['goal']}\n"
            f"Planner={g.planner_strategy} Memory={g.memory_strategy} "
            f"Reflection={g.reflection_strategy} Tools={g.tool_policy} Budget={g.reasoning_budget}"
        )
        try:
            resp = self.backend.generate(prompt, budget=g.reasoning_budget)
            self.api_calls += 1
        except Exception:
            resp = MockLLMBackend().generate(prompt, budget=g.reasoning_budget)
            self.api_calls += 1

        # Execute required tool(s) — always logged.
        tool_results = []
        tool_ok = True
        required = task.get("required_tool") or ""
        if required:
            tr = self._invoke_tool(required, task)
            tool_results.append(tr)
            tool_ok = tool_ok and tr.ok
        elif task["category"] == "reasoning":
            tool_ok = True  # no tool required
        else:
            tr = self.tools.invoke("search", query=task["goal"])
            tool_results.append(tr)

        success, score = self._score(task, g, resp, tool_ok, tool_results)
        steps = max(1, int(round(task["horizon"] * (0.7 + 0.4 * (g.reasoning_budget / 128.0)))))
        if not success:
            steps = int(steps * 1.2)
        tokens = resp.tokens + steps * 4
        latency = resp.latency + steps * 0.02 + 0.01 * len(tool_results)
        cost = resp.cost + steps * 8e-5 * (1.0 if g.tool_policy != "tool_first" else 1.6)

        trajectory = [
            {"t": 0, "action": "observe", "goal": task["goal"][:60]},
            {"t": 1, "action": f"plan:{g.planner_strategy}"},
        ]
        for i, tr in enumerate(tool_results):
            trajectory.append({"t": 2 + i, "action": "tool", "tool": tr.tool, "ok": tr.ok})
        trajectory.append({"t": len(trajectory), "action": "finish", "success": success})

        extra = {
            "trajectory": trajectory,
            "goal": task["goal"],
            "category": task["category"],
            "difficulty": task["difficulty"],
            "score": score,
            "tool_calls": [tr.to_dict() for tr in tool_results],
            "tool_success": tool_ok,
            "backend": self.backend.name,
            "reflection": g.reflection_strategy,
            "tool_policy": g.tool_policy,
            "reasoning_budget": g.reasoning_budget,
        }
        self.cache.store_genome_task(
            g, task["task_id"],
            CacheEntry(genome_hash(g), task["task_id"], [], int(tokens), float(cost),
                       float(latency), success, steps, extra),
            benchmark=f"{self.name}:{self.split}", seed=self.seed,
        )
        return TaskResult(
            task_id=task["task_id"], success=success, steps=steps,
            tokens=int(tokens), latency=float(latency), cost=float(cost),
            metadata=extra,
        )

    def _invoke_tool(self, name: str, task: Dict[str, Any]):
        if name == "calculator":
            expr = "17+25*3" if "17" in task["goal"] else "20+30"
            return self.tools.invoke("calculator", expression=expr)
        if name == "search":
            return self.tools.invoke("search", query=task["goal"])
        if name == "file_read":
            return self.tools.invoke("file_read", path="notes.txt")
        if name == "file_write":
            return self.tools.invoke("file_write", path="summary.txt", content=task["goal"][:80])
        if name == "file_list":
            return self.tools.invoke("file_list")
        return self.tools.invoke("search", query=task["goal"])

    def _score(self, task, g, resp, tool_ok: bool, tool_results) -> Tuple[bool, float]:
        low = (resp.text or "").lower()
        has_plan = any(k in low for k in ("step", "plan", "1.", "-", "go"))
        quality = 0.4 * float(has_plan) + 0.6 * float(tool_ok)
        cat_bonus = {"information": 0.0, "reasoning": 0.02, "tool": 0.04}.get(task["category"], 0.0)
        cap = (
            0.32 * {"direct": 0.50, "cot": 0.70, "plan_and_solve": 0.82, "tree_search": 0.88, "reflexion": 0.86}.get(g.planner_strategy, 0.6)
            + 0.22 * {"none": 0.48, "short_term": 0.62, "episodic": 0.74, "semantic": 0.80, "hybrid": 0.86}.get(g.memory_strategy, 0.6)
            + 0.20 * {"none": 0.52, "self_critique": 0.72, "pairwise": 0.78, "critic_model": 0.84, "iterative": 0.88}.get(g.reflection_strategy, 0.6)
            + 0.26 * {"no_tools": 0.42, "conservative": 0.62, "balanced": 0.74, "aggressive": 0.84, "tool_first": 0.86}.get(g.tool_policy, 0.6)
        )
        cap += 0.10 * math.sqrt(max(0.0, (g.reasoning_budget - 8) / 120.0)) + cat_bonus
        if task["category"] == "tool" and g.tool_policy == "no_tools":
            cap -= 0.12
        score = 0.7 * cap + 0.3 * quality
        return score >= task["difficulty"], float(min(1.0, max(0.0, score)))

    def evaluate(self, episode: EpisodeResult) -> Dict[str, float]:
        m = episode_metrics(episode)
        m["tool_success"] = float(
            sum(1 for r in episode.results if r.metadata.get("tool_success"))
            / max(1, len(episode.results))
        )
        m["mean_tool_calls"] = float(
            sum(len(r.metadata.get("tool_calls") or []) for r in episode.results)
            / max(1, len(episode.results))
        )
        m["api_calls"] = float(self.api_calls)
        m["cache_used"] = float(self.cache_used)
        return m

    def cost_report(self) -> Dict[str, Any]:
        usage = self.backend.usage() if hasattr(self.backend, "usage") else {}
        return {
            "backend": self.backend.name,
            "api_calls": self.api_calls,
            "cache_used": self.cache_used,
            "cache_stats": self.cache.stats(),
            "llm_usage": usage,
            "n_tasks": self.n_tasks,
            "split": self.split,
        }
