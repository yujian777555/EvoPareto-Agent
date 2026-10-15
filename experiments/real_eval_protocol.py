"""Phase5-R3-R1 fair experiment protocol.

- Content-level train/test isolation (task_fingerprint)
- Preference-aware selection (not fitness_vector[0] for every pref)
- Independent held-out evaluation (no train-cache reuse)
- Budget gate BEFORE requests
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.evaluation_kind import classify_experiment
from src.evaluation.metrics import preference_satisfaction_score
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.preference import encode_preference
from src.runtime.cache import EvaluationCache
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline
from src.runtime.task_split import (
    assert_no_content_leakage,
    detect_task_leakage,
    split_by_fingerprint,
    task_fingerprint,
)


def select_by_preference(
    individuals: Sequence[Individual],
    preference: Any,
) -> Individual:
    """PPEC-consistent selection: maximize Preference Satisfaction Score.

    Cost is minimized inside preference_satisfaction (1-cost); other objectives
    maximize. This replaces the buggy fitness_vector[0] argmax for all prefs.
    """
    if not individuals:
        raise ValueError("empty population")
    pref = encode_preference(preference)
    scored = []
    for ind in individuals:
        if not ind.has_fitness():
            continue
        scored.append((preference_satisfaction_score([ind.fitness_vector], pref), ind))
    if not scored:
        raise ValueError("no evaluated individuals")
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


def selection_difference(
    pop_a: Sequence[Individual],
    pop_b: Sequence[Individual],
    preference: Any,
) -> Dict[str, Any]:
    """Do two methods select different argmax genomes under the same pref?"""
    a = select_by_preference(pop_a, preference)
    b = select_by_preference(pop_b, preference)
    return {
        "same_genome": a.genome.key() == b.genome.key(),
        "genome_a": a.genome.to_dict(),
        "genome_b": b.genome.to_dict(),
        "pss_a": preference_satisfaction_score([a.fitness_vector], encode_preference(preference)),
        "pss_b": preference_satisfaction_score([b.fitness_vector], encode_preference(preference)),
    }


def heldout_suite(tasks: Sequence[Dict[str, Any]], train_frac: float = 0.7):
    """Return (train_tasks, test_tasks, leak_report)."""
    train, test = split_by_fingerprint(tasks, train_frac=train_frac)
    rep = detect_task_leakage(train, test)
    return train, test, rep


def independent_test_eval(
    genome: AgentGenome,
    *,
    benchmark: str,
    backend: str,
    seed: int,
    n_tasks: int = 20,
    cache: EvaluationCache,
    test_tasks: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Evaluate frozen genome on held-out *content*, isolated cache."""
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=n_tasks, backend=backend, seed=seed, benchmark=benchmark),
        cache=cache,
    )
    if test_tasks is not None and hasattr(pipe.adapter, "_build_tasks"):
        # Inject content-level split tasks (not just seed).
        pipe.adapter._tasks = list(test_tasks)[:n_tasks]
        if hasattr(pipe.adapter, "n"):
            pipe.adapter.n = len(pipe.adapter._tasks)
    if hasattr(pipe.adapter, "reset") and test_tasks is None:
        pipe.adapter.reset()
    agent = pipe.builder.build(genome, agent_id=0)
    ep, recs = pipe.adapter.run_recorded(agent)
    vec = pipe.objectives.from_episode(ep)
    fps = [task_fingerprint({"task_id": r.task_id, "goal": r.metadata.get("goal", ""),
                             "difficulty": r.metadata.get("difficulty", 0),
                             "hint": ""}) for r in recs]
    return {
        "genome": genome.to_dict(),
        "objectives": vec,
        "success": vec[0],
        "cost": vec[2],
        "n_tasks": ep.n_tasks,
        "task_fingerprints": fps,
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
    """Train under each preference; independent held-out test; no mock fallback."""
    planned = pop * (gens + 1) * train_tasks * 3 + 3 * test_tasks
    if planned > budget_cap_calls:
        raise RuntimeError(f"budget pre-check failed: {planned} > {budget_cap_calls}")

    # Build full catalog then content-split.
    from src.benchmark.real_world_agent import _build_catalog

    catalog = _build_catalog()
    train_cat, test_cat, leak = heldout_suite(catalog)
    out: Dict[str, Any] = {
        "benchmark": benchmark,
        "seed": seed,
        "planned_calls": planned,
        "leak_report": leak.to_dict(),
        "evaluation_kind": classify_experiment(backend, api_ok=True, native_env=False),
        "results": {},
    }
    if not leak.ok:
        out["status"] = "BLOCKED_TASK_LEAKAGE"
        return out

    for pref in ("accuracy_first", "cost_first", "balanced"):
        cache_train = EvaluationCache()
        pipe = RealLLMPipeline(
            RealLLMConfig(n_tasks=min(train_tasks, len(train_cat)), backend=backend,
                          seed=seed, benchmark=benchmark),
            cache=cache_train,
        )
        if hasattr(pipe.adapter, "_build_tasks"):
            pipe.adapter._tasks = list(train_cat)[:train_tasks]
        cfg = MemoryEvolutionConfig(
            pop_size=pop, n_offspring=pop, seed=seed,
            use_adaptive=True, experience_mode="robust_peem", preference=pref,
        )
        loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
        loop.initialize()
        loop.run(gens)
        best = select_by_preference(loop.individuals, pref)
        test_cache = EvaluationCache()
        test = independent_test_eval(
            best.genome, benchmark=benchmark, backend=backend,
            seed=seed + 10_000, n_tasks=min(test_tasks, len(test_cat)),
            cache=test_cache, test_tasks=test_cat,
        )
        out["results"][pref] = {
            "train_pss": preference_satisfaction_score(
                [best.fitness_vector or [0] * 5], encode_preference(pref)
            ),
            "selected_genome": best.genome.to_dict(),
            "test": test,
        }
    return out


def reclassify_existing_results() -> Dict[str, str]:
    root = Path(__file__).resolve().parents[1] / "results"
    mapping = {
        "ablation": "simulated",
        "benchmark_extension": "simulated",
        "real_world": "simulated",
        "real_llm": "real_llm_proxy_partial",
        "real_llm_large": "simulated_or_pending",
        "final_real_llm": "real_llm_proxy",
    }
    return {k: v for k, v in mapping.items() if (root / k).exists()}
