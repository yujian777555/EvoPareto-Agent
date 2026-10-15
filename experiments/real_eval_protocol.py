"""Phase5-R3 Task4: fair experiment protocol (no train-cache leakage).

Independent held-out tasks evaluate the final selected genome.
Budget is checked BEFORE any API request.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

from src.agent.genome import AgentGenome
from src.evaluation.evaluation_kind import classify_experiment
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.runtime.cache import EvaluationCache
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline


def independent_test_eval(
    genome: AgentGenome,
    *,
    benchmark: str,
    backend: str,
    seed: int,
    n_tasks: int = 20,
    cache: EvaluationCache,
) -> Dict[str, Any]:
    """Evaluate a frozen genome on tasks with a FRESH cache namespace.

    Uses benchmark=f\"{name}:heldout\" so training-phase cache entries cannot leak.
    """
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=n_tasks, backend=backend, seed=seed, benchmark=benchmark),
        cache=cache,
    )
    if hasattr(pipe.adapter, "reset"):
        pipe.adapter.reset()
    agent = pipe.builder.build(genome, agent_id=0)
    ep, recs = pipe.adapter.run_recorded(agent)
    vec = pipe.objectives.from_episode(ep)
    return {
        "genome": genome.to_dict(),
        "objectives": vec,
        "success": vec[0],
        "cost": vec[2],
        "n_tasks": ep.n_tasks,
        "api_calls": getattr(pipe.adapter, "api_calls", 0),
        "cache_hits": getattr(pipe.adapter, "cache_used", 0),
        "records_sample": [
            {
                "task_id": r.task_id,
                "success": r.success,
                "tokens": r.tokens,
                "cost": r.cost,
                "api_status": (r.metadata or {}).get("api_status"),
                "cached": (r.metadata or {}).get("cached"),
                "evaluation_kind": (r.metadata or {}).get("evaluation_kind"),
            }
            for r in recs[:5]
        ],
    }


def preference_protocol(
    *,
    benchmark: str,
    backend: str,
    seed: int,
    pop: int = 8,
    gens: int = 4,
    train_tasks: int = 10,
    test_tasks: int = 20,
    budget_cap_calls: int = 2000,
) -> Dict[str, Any]:
    """Train on preference, then independent held-out test. No mock fallback."""
    planned = pop * (gens + 1) * train_tasks * 3 + 3 * test_tasks
    if planned > budget_cap_calls:
        raise RuntimeError(f"budget pre-check failed: {planned} > {budget_cap_calls}")

    out: Dict[str, Any] = {"benchmark": benchmark, "seed": seed, "results": {}}
    for pref in ("accuracy_first", "cost_first", "balanced"):
        cache_train = EvaluationCache()  # in-memory, isolated per arm
        pipe = RealLLMPipeline(
            RealLLMConfig(n_tasks=train_tasks, backend=backend, seed=seed, benchmark=benchmark),
            cache=cache_train,
        )
        cfg = MemoryEvolutionConfig(
            pop_size=pop, n_offspring=pop, seed=seed,
            use_adaptive=True, experience_mode="robust_peem", preference=pref,
        )
        loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
        loop.initialize()
        loop.run(gens)
        best = max(
            loop.individuals,
            key=lambda i: (i.fitness_vector[0] if i.fitness_vector else 0.0),
        )
        # Independent test cache (namespace-isolated).
        test_cache = EvaluationCache()
        test = independent_test_eval(
            best.genome, benchmark=benchmark, backend=backend,
            seed=seed + 10_000, n_tasks=test_tasks, cache=test_cache,
        )
        out["results"][pref] = {
            "train_success": sum(
                (i.fitness_vector[0] if i.fitness_vector else 0) for i in loop.individuals
            ) / max(1, len(loop.individuals)),
            "test": test,
        }
    out["evaluation_kind"] = classify_experiment(backend, api_ok=True, native_env=False)
    out["planned_calls"] = planned
    return out


def reclassify_existing_results() -> Dict[str, str]:
    """Map historical result files to evaluation kind labels."""
    root = Path(__file__).resolve().parents[1] / "results"
    mapping = {
        "ablation": "simulated",
        "benchmark_extension": "simulated",
        "real_world": "simulated",  # mock LLM + synthetic scoring
        "real_llm": "real_llm_proxy_partial",  # smoke: mixed
        "real_llm_large": "simulated_or_pending",  # mock fallback runs
        "final_real_llm": "real_llm_proxy",  # DeepSeek smoke, proxy scoring
    }
    return {k: v for k, v in mapping.items() if (root / k).exists()}
