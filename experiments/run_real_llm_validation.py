"""Phase 4-R1: Real LLM agent validation (DeepSeek/OpenAI + cache).

Pipeline smoke first (tiny), then controlled scale.

Usage:
    python experiments/run_real_llm_validation.py              # smoke + config
    python experiments/run_real_llm_validation.py --scale paper
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import hypervolume, igd, preference_satisfaction_score, reference_front_from_population
from src.evolution.preference import encode_preference
from src.runtime.real_llm_pipeline import RealLLMPipeline, RealLLMConfig, run_real_llm_evolution

OUT = ROOT / "results" / "real_llm" / "alfworld"


def _ms(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    if not n:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    return {"mean": m, "std": var ** 0.5}


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def smoke_run() -> Dict[str, Any]:
    """Tiny end-to-end to verify pipeline + API + cache."""
    print("SMOKE: pop=4 gens=2 tasks=3", flush=True)
    t0 = time.time()
    out = run_real_llm_evolution(
        n_tasks=3, pop_size=4, n_generations=2, seed=1, backend="auto",
        cache_path=str(OUT / "cache_smoke.json"),
    )
    return {
        "ok": True,
        "wall_time": time.time() - t0,
        "backend": out["backend"],
        "model": out["model"],
        "final_hv": out["final_hypervolume"],
        "cost_report": out["cost_report"],
        "llm_usage": out["cost_report"].get("llm_usage", {}),
    }


def baseline_table(scale: str = "smoke", backend: str = "auto") -> Dict[str, Any]:
    """B0–B4 comparison."""
    if scale == "smoke":
        n_tasks, pop, gens, seeds = 3, 5, 2, [11]
    elif scale == "paper":
        n_tasks, pop, gens, seeds = 20, 16, 10, [11, 22, 33]
    else:  # pilot
        n_tasks, pop, gens, seeds = 10, 8, 5, [11, 22]

    variants = {
        "B0_random_search": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "B2_nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "B3_nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "B4_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
    }
    runs = []
    # B1 ReAct fixed genome
    from src.agent.genome import AgentGenome

    pipe = RealLLMPipeline(RealLLMConfig(n_tasks=n_tasks, seed=seeds[0], backend=backend,
                                         cache_path=str(OUT / "cache_baselines.json")))
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    vec = pipe.evaluate_genome(react)
    runs.append({"variant": "B1_react", "seed": seeds[0], "objectives": vec, "success": vec[0], "cost": vec[2]})

    for seed in seeds:
        for name, kw in variants.items():
            print(f"  {name} seed={seed} backend={backend}", flush=True)
            out = run_real_llm_evolution(
                n_tasks=n_tasks, pop_size=pop, n_generations=gens, seed=seed,
                backend=backend, cache_path=str(OUT / "cache_baselines.json"), **kw
            )
            ff = out["front_fitness"]
            runs.append({
                "variant": name,
                "seed": seed,
                "final_hv": out["final_hypervolume"],
                "final_pareto": out["final_pareto_size"],
                "success": sum(r[0] for r in ff) / len(ff) if ff else 0.0,
                "cost": sum(r[2] for r in ff) / len(ff) if ff else 0.0,
                "efficiency": sum(r[1] for r in ff) / len(ff) if ff else 0.0,
                "usage": out["cost_report"].get("llm_usage", {}),
                "cache": out["cost_report"].get("cache", {}),
            })
    summary = {}
    for name in ["B1_react"] + list(variants):
        sub = [r for r in runs if r["variant"] == name]
        summary[name] = {
            "success": _ms([r.get("success", 0.0) for r in sub]),
            "cost": _ms([r.get("cost", 0.0) for r in sub]),
        }
        if name != "B1_react":
            summary[name]["final_hv"] = _ms([r.get("final_hv", 0.0) for r in sub])
    return {"scale": scale, "config": {"n_tasks": n_tasks, "pop": pop, "gens": gens, "seeds": seeds},
            "runs": runs, "summary": summary}


def preference_runs(scale: str = "smoke", backend: str = "auto") -> Dict[str, Any]:
    if scale == "smoke":
        n_tasks, pop, gens, seeds = 3, 5, 2, [5]
    elif scale == "paper":
        n_tasks, pop, gens, seeds = 20, 16, 10, [5, 15]
    else:
        n_tasks, pop, gens, seeds = 10, 8, 5, [5]

    prefs = ["accuracy_first", "cost_first", "balanced"]
    runs = []
    for seed in seeds:
        for pref in prefs:
            print(f"  pref={pref} seed={seed} backend={backend}", flush=True)
            out = run_real_llm_evolution(
                n_tasks=n_tasks, pop_size=pop, n_generations=gens, seed=seed,
                backend=backend, preference=pref,
                cache_path=str(OUT / "cache_prefs.json"),
            )
            ff = out["front_fitness"]
            p = encode_preference(pref)
            runs.append({
                "preference": pref,
                "seed": seed,
                "pref_sat": preference_satisfaction_score(ff, p) if ff else 0.0,
                "success": sum(r[0] for r in ff) / len(ff) if ff else 0.0,
                "cost": sum(r[2] for r in ff) / len(ff) if ff else 0.0,
                "final_hv": out["final_hypervolume"],
            })
    summary = {}
    for pref in prefs:
        sub = [r for r in runs if r["preference"] == pref]
        summary[pref] = {
            "pref_sat": _ms([r["pref_sat"] for r in sub]),
            "success": _ms([r["success"] for r in sub]),
            "cost": _ms([r["cost"] for r in sub]),
        }
    return {"runs": runs, "summary": summary}


def evolution_history(scale: str = "smoke", backend: str = "auto") -> Dict[str, Any]:
    gens = 2 if scale == "smoke" else (5 if scale != "paper" else 10)
    pop = 5 if scale == "smoke" else (8 if scale != "paper" else 16)
    n_tasks = 3 if scale == "smoke" else 10
    out = run_real_llm_evolution(
        n_tasks=n_tasks, pop_size=pop, n_generations=gens, seed=42,
        backend=backend, preference="accuracy_first",
        cache_path=str(OUT / "cache_history.json"),
    )
    marks = [0, gens // 2, gens]
    traj = []
    for g in marks:
        if g < len(out["history"]):
            traj.append({"generation": g, **{k: out["history"][g].get(k) for k in
                        ("hypervolume", "n_non_dominated", "mutation_entropy", "temperature")}})
    return {"trajectory": traj, "final_hv": out["final_hypervolume"],
            "usage": out["cost_report"].get("llm_usage", {}),
            "cache": out["cost_report"].get("cache", {})}


def main() -> Dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", choices=["smoke", "pilot", "paper"], default="smoke")
    ap.add_argument("--backend", choices=["auto", "mock", "deepseek", "openai"], default="auto")
    ap.add_argument("--skip-smoke", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    smoke = {} if args.skip_smoke else smoke_run()
    _write(OUT / "smoke.json", smoke)
    print("SMOKE:", json.dumps({k: smoke.get(k) for k in ("ok", "backend", "model", "final_hv")}, indent=2), flush=True)

    print("BASELINES...", flush=True)
    bas = baseline_table(args.scale, backend=args.backend)
    _write(OUT / "baseline_results.json", bas)

    print("PREFERENCES...", flush=True)
    prefs = preference_runs(args.scale, backend=args.backend)
    _write(OUT / "preference_results.json", prefs)

    print("HISTORY...", flush=True)
    hist = evolution_history(args.scale, backend=args.backend)
    _write(OUT / "evolution_history.json", hist)

    # Pareto front of the last baseline PEEM-PPEC run.
    last = [r for r in bas["runs"] if r["variant"] == "B4_peem_ppec"]
    _write(OUT / "pareto_front.json", {"runs": last})

    # Cost report
    all_usage = []
    for pack in (bas, prefs):
        for r in pack.get("runs", []):
            if "usage" in r:
                all_usage.append(r["usage"])
    total_tokens = sum(u.get("tokens", 0) for u in all_usage)
    total_cost = sum(u.get("cost", 0.0) for u in all_usage)
    total_calls = sum(u.get("calls", 0) for u in all_usage)
    cost_report = {
        "scale": args.scale,
        "llm_calls": total_calls,
        "tokens": total_tokens,
        "estimated_cost_usd": total_cost,
        "budget_cap_usd": 20.0,
        "within_budget": total_cost <= 20.0,
        "smoke": smoke.get("llm_usage", {}),
    }
    _write(OUT / "cost_report.json", cost_report)

    summary = {
        "scale": args.scale,
        "smoke": {k: smoke.get(k) for k in ("ok", "backend", "model", "final_hv")},
        "baselines": bas["summary"],
        "preferences": prefs["summary"],
        "trajectory": hist["trajectory"],
        "cost_report": cost_report,
    }
    _write(OUT / "summary.json", summary)
    print("Phase 4-R1 real-LLM validation complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
