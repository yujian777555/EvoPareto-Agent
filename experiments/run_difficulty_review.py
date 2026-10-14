"""Phase5-Audit-5: benchmark difficulty review & harder real-world mode.

Checks baseline saturation (e.g. ReAct success = 1.0) and measures a
**hard** environment profile: longer horizon, noisy tools, budget caps.

Environment-only changes; algorithms untouched.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.benchmark.real_world_agent import RealWorldAgentBenchmark, _build_catalog
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.runtime.agent_builder import AgentBuilder
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "audit"


def saturation_check() -> dict:
    """Measure ReAct / evolved success on current catalog."""
    catalog = _build_catalog()
    difficulties = [t["difficulty"] for t in catalog]
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    b = RealWorldAgentBenchmark(n_tasks=50, seed=0)
    agent = AgentBuilder().build(react)
    ep = b.run(agent)
    return {
        "n_tasks": len(catalog),
        "difficulty_mean": sum(difficulties) / len(difficulties),
        "difficulty_max": max(difficulties),
        "react_success": ep.success_rate,
        "saturated": ep.success_rate >= 0.98,
    }


def hard_profile_metrics(seed: int) -> dict:
    """Run ReAct and PEEM on a difficulty-boosted clone of the catalog."""
    # Environment-only: raise difficulty further and shrink budget effect.
    catalog = _build_catalog()
    for t in catalog:
        t["difficulty"] = min(0.98, t["difficulty"] + 0.08)

    class HardBenchmark(RealWorldAgentBenchmark):
        def _build_tasks(self):
            tasks = []
            for i in range(self.n):
                tpl = catalog[i % len(catalog)]
                tasks.append({**tpl, "task_id": f"{tpl['task_id']}-hard-{self.seed}-{i:03d}"})
            return tasks

        def _score(self, task, g, resp, tool_ok, tool_results):
            # Noisy tools: required tool can fail depending on tool policy.
            ok = tool_ok
            if task.get("required_tool") and g.tool_policy == "no_tools":
                ok = False
            return super()._score(task, g, resp, ok, tool_results)

    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    pipe = RealLLMPipeline(RealLLMConfig(n_tasks=30, backend="mock", seed=seed))
    pipe.adapter = HardBenchmark(n_tasks=30, seed=seed, backend=pipe.backend, cache=None)
    agent = AgentBuilder().build(react)
    ep = pipe.adapter.run(agent)
    react_succ = ep.success_rate

    cfg = MemoryEvolutionConfig(
        pop_size=10, n_offspring=10, seed=seed,
        use_adaptive=True, experience_mode="robust_peem",
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    loop.run(5)
    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    peem_succ = sum(r[0] for r in rows) / len(rows) if rows else 0.0
    return {
        "seed": seed,
        "react_success": react_succ,
        "peem_success": peem_succ,
        "peem_final_hv": loop.current_hypervolume(),
        "n_front": len(loop.pareto_front()),
    }


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    sat = saturation_check()
    print("SATURATION", json.dumps(sat, indent=2))
    hard_runs = [hard_profile_metrics(s) for s in (11, 22, 33)]
    mean_react = sum(r["react_success"] for r in hard_runs) / len(hard_runs)
    mean_peem = sum(r["peem_success"] for r in hard_runs) / len(hard_runs)
    payload = {
        "phase": "Phase5-Audit-5 benchmark difficulty",
        "saturation_check": sat,
        "hard_profile": {
            "description": (
                "difficulty +0.08, no_tools penalized on tool tasks, "
                "environment-only hardening"
            ),
            "runs": hard_runs,
            "mean_react_success": mean_react,
            "mean_peem_success": mean_peem,
            "still_saturated": mean_react >= 0.98 and mean_peem >= 0.98,
        },
        "recommendation": (
            "If still saturated, paper should report ceiling effects on mock "
            "real-world tasks and rely on ALFWorld/WebShop/DeepSeek for "
            "discriminative power; do not silently retune tasks to inflate PEEM."
        ),
    }
    (OUT / "difficulty_review.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(payload["hard_profile"], indent=2))
    return payload


if __name__ == "__main__":
    main()
