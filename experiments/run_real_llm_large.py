"""Phase5-R3 experiment runner (large-scale real LLM).

If DeepSeek chat API is unreachable, records API status and can fall back to
mock **with explicit labeling** so results are never misread as live-LLM.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backend.http_client import post_json
from src.evaluation.metrics import hypervolume, igd, preference_satisfaction_score, reference_front_from_population
from src.evolution.memory_evolution import MemoryEvolutionConfig
from src.evolution.operator_logging import LoggingLoop, OPERATORS
from src.evolution.preference import encode_preference
from src.runtime.cache import EvaluationCache
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "real_llm_large"

CONFIG = {
    "pop": 8,
    "gens": 4,
    "tasks": 10,
    "seeds": [11, 22, 33],
    "methods": ["B1_nsga3", "B2_nsga3_peem", "B3_peem_ppec"],
    "workers": 6,
    "budget_calls": 5000,
}


def api_healthcheck() -> Dict[str, Any]:
    """Probe DeepSeek chat; never fabricate success on empty bodies."""
    from src.backend.diagnostics import check_balance, chat_probe

    bal = check_balance()
    probe = chat_probe("deepseek-flash", stream=False, thinking_disabled=True,
                       max_tokens=64, timeout=12)
    return {
        "ok": bool(probe.get("ok")),
        "model_id": "deepseek-flash",
        "balance_available": bal.get("available"),
        "chat_nonstream": probe,
        "reason": probe.get("error") or ("empty_body" if not probe.get("valid_completion") else None),
    }


def assert_budget_before_calls(planned_calls: int, budget_cap: int) -> None:
    """P0: budget gate BEFORE any API request."""
    if planned_calls < 0:
        raise ValueError("planned_calls must be >= 0")
    if planned_calls > budget_cap:
        raise RuntimeError(
            f"budget exceeded before requests: planned={planned_calls} > cap={budget_cap}"
        )


def _ms(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    if not n:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / n
    return {"mean": m, "std": var ** 0.5}


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def run_method(method: str, *, benchmark: str, seed: int, backend: str) -> Dict[str, Any]:
    t0 = time.time()
    cache = EvaluationCache(OUT / f"cache_{benchmark}.json")
    pipe = RealLLMPipeline(
        RealLLMConfig(
            n_tasks=CONFIG["tasks"], backend=backend, seed=seed,
            benchmark=benchmark, cache_path=str(OUT / f"cache_{benchmark}.json"),
        ),
        cache=cache,
    )
    if hasattr(pipe.adapter, "max_workers"):
        pipe.adapter.max_workers = CONFIG["workers"]

    use_adaptive = method != "B1_nsga3"
    experience_mode = "robust_peem" if use_adaptive else "phase2"
    preference = "balanced" if method == "B3_peem_ppec" else None
    mcfg = MemoryEvolutionConfig(
        pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
        use_adaptive=use_adaptive, experience_mode=experience_mode,
        preference=preference,
    )
    loop = LoggingLoop(evaluator=pipe.as_evaluate_fn(), config=mcfg)
    loop.logger.benchmark = f"{benchmark}:{method}"
    loop.logger.seed = seed
    loop.initialize()
    episodes = []
    for ind in loop.individuals[:2]:
        _, _, recs = pipe.evaluate_genome_recorded(ind.genome)
        for r in recs:
            episodes.append({
                "task_id": r.task_id, "benchmark": benchmark, "method": method,
                "generation": 0, "genome": ind.genome.to_dict(),
                "success": r.success, "steps": r.steps, "tokens": r.tokens,
                "latency": r.latency, "cost": r.cost,
                "trajectory": r.trajectory,
                "model": getattr(pipe.backend, "model", "unknown"),
            })
    loop.run(CONFIG["gens"])
    front = loop.pareto_front()
    ff = [list(i.fitness_vector or []) for i in front]
    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    usage = pipe.backend.usage() if hasattr(pipe.backend, "usage") else {}
    return {
        "method": method, "benchmark": benchmark, "seed": seed,
        "backend": backend, "model": getattr(pipe.backend, "model", "unknown"),
        "final_hv": loop.current_hypervolume(), "final_pareto": len(ff),
        "success": sum(r[0] for r in rows) / len(rows) if rows else 0.0,
        "cost": sum(r[2] for r in rows) / len(rows) if rows else 0.0,
        "efficiency": sum(r[1] for r in rows) / len(rows) if rows else 0.0,
        "pss": preference_satisfaction_score(rows, encode_preference("balanced")) if rows else 0.0,
        "front_rows": ff, "population_rows": rows,
        "curve": list(loop.history),
        "operator_snapshots": loop.logger.to_dict(),
        "episodes": episodes,
        "usage": usage, "cache": cache.stats(),
        "wall_time": time.time() - t0,
    }


def experiment_main(benchmark: str, backend: str) -> Dict[str, Any]:
    print(f"=== Main {benchmark} backend={backend} ===", flush=True)
    runs = []
    for seed in CONFIG["seeds"]:
        for method in CONFIG["methods"]:
            print(f"  {method} seed={seed}", flush=True)
            r = run_method(method, benchmark=benchmark, seed=seed, backend=backend)
            runs.append(r)
            _write(OUT / f"{benchmark}_partial.json", {
                "backend": backend,
                "runs": [{k: v for k, v in rr.items()
                          if k not in ("front_rows", "population_rows", "episodes", "operator_snapshots")}
                         for rr in runs],
            })
    all_rows = [row for r in runs for row in r["population_rows"]]
    ref = reference_front_from_population(all_rows) if all_rows else []
    for r in runs:
        r["igd"] = igd(r.get("front_rows") or [], ref) if ref else 0.0
    table = []
    for method in CONFIG["methods"]:
        sub = [r for r in runs if r["method"] == method]
        table.append({
            "Method": method,
            "Success": _ms([r["success"] for r in sub]),
            "HV": _ms([r["final_hv"] for r in sub]),
            "IGD": _ms([r["igd"] for r in sub]),
            "Cost": _ms([r["cost"] for r in sub]),
            "TokensProxy": _ms([1.0 - r["efficiency"] for r in sub]),
        })
    slim = [{k: v for k, v in r.items() if k not in ("front_rows", "population_rows")} for r in runs]
    return {"benchmark": benchmark, "backend": backend, "config": CONFIG, "table": table, "runs": slim}


def main() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    health = api_healthcheck()
    # P0: real experiment must NOT fall back to mock and emit paper tables.
    if not health.get("ok"):
        meta = {
            "phase": "Phase5-R3 large-scale real LLM",
            "intended_model": "deepseek-flash",
            "api_healthcheck": health,
            "backend_used": "none",
            "live_llm_evidence": False,
            "aborted": True,
            "abort_reason": "DeepSeek chat API unavailable; real experiment stopped",
            "config": CONFIG,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _write(OUT / "meta.json", meta)
        print("API unavailable — abort real experiment (no mock fallback).")
        print(json.dumps(health, indent=2, ensure_ascii=False))
        return meta

    backend = "deepseek"
    # Pre-flight budget: each run evaluates pop*(gens+1)*tasks genomes×tasks.
    planned_per_run = CONFIG["pop"] * (CONFIG["gens"] + 1) * CONFIG["tasks"]
    n_runs = len(CONFIG["seeds"]) * len(CONFIG["methods"]) * 2  # alfworld+webshop
    assert_budget_before_calls(planned_per_run * n_runs, CONFIG["budget_calls"])

    meta = {
        "phase": "Phase5-R3 large-scale real LLM",
        "intended_model": "deepseek-flash",
        "api_healthcheck": health,
        "backend_used": backend,
        "live_llm_evidence": True,
        "aborted": False,
        "planned_calls": planned_per_run * n_runs,
        "config": CONFIG,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write(OUT / "meta.json", meta)
    print("API health:", json.dumps(health, ensure_ascii=False), flush=True)
    print("backend:", backend, flush=True)

    alf = experiment_main("alfworld", backend)
    _write(OUT / "alfworld.json", alf)
    web = experiment_main("webshop", backend)
    _write(OUT / "webshop.json", web)
    _write(OUT / "ablation.json", {"alfworld": alf["table"], "webshop": web["table"]})

    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    hits = misses = 0
    for pack in (alf, web):
        for r in pack["runs"]:
            u = r.get("usage") or {}
            total_calls += int(u.get("calls", 0))
            total_tokens += int(u.get("tokens", 0))
            total_cost += float(u.get("cost", 0.0))
            cs = r.get("cache") or {}
            hits += int(cs.get("hits", 0))
            misses += int(cs.get("misses", 0))
    cost = {
        "total_api_calls": total_calls,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "cache_hits": hits,
        "cache_misses": misses,
        "budget_cap_calls": CONFIG["budget_calls"],
        "within_budget": total_calls <= CONFIG["budget_calls"],
        "api_healthcheck": health,
        "backend_used": backend,
        "live_llm_evidence": bool(health.get("ok")) and backend != "mock",
    }
    _write(OUT / "cost_analysis.json", cost)
    traj = {
        bench: [
            {"seed": r["seed"],
             "curve": [{"generation": h.get("generation"), "hypervolume": h.get("hypervolume")}
                       for h in r.get("curve", [])]}
            for r in pack["runs"] if r["method"] == "B3_peem_ppec"
        ]
        for bench, pack in (("alfworld", alf), ("webshop", web))
    }
    _write(OUT / "trajectories.json", traj)

    summary = {"meta": meta, "alfworld": alf["table"], "webshop": web["table"], "cost_analysis": cost}
    _write(OUT / "summary.json", summary)
    print("Phase5-R3 complete. live_llm_evidence=", cost["live_llm_evidence"])
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:2500])
    return summary


if __name__ == "__main__":
    main()
