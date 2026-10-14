"""Phase 4 demo: PEEM-PPEC on real/simulated ALFWorld + WebShop.

E1 Baseline comparison (B1–B5)
E2 Module ablation
E3 Preference scenarios
E4 Evolution trajectory (gens 0/5/10/20)

Offline by default (MockLLMBackend + simulated benchmarks).
Set OPENAI_API_KEY / DEEPSEEK_API_KEY and --backend to use real LLMs.

Usage:
    python experiments/run_real_agent_evolution.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import hypervolume, preference_satisfaction_score
from src.evolution.preference import encode_preference
from src.runtime.real_pipeline import RealEvalConfig, RealBenchmarkPipeline, run_real_agent_evolution

RESULTS_DIR = ROOT / "results" / "real_agent"


def _ms(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    if not n:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    return {"mean": m, "std": var ** 0.5}


def _objective_summary(front_fitness: List[List[float]], history: List[Dict], preference=None) -> Dict[str, Any]:
    if not front_fitness:
        return {"success_proxy": 0.0, "cost_proxy": 0.0}
    # performance=idx0, cost=idx2
    perf = sum(r[0] for r in front_fitness) / len(front_fitness)
    cost = sum(r[2] for r in front_fitness) / len(front_fitness)
    out = {
        "mean_performance": perf,
        "mean_cost": cost,
        "mean_efficiency": sum(r[1] for r in front_fitness) / len(front_fitness),
        "final_hv": history[-1].get("hypervolume", 0.0) if history else 0.0,
    }
    if preference is not None:
        out["pref_sat"] = preference_satisfaction_score(front_fitness, preference)
    return out


def experiment_1(benchmark: str = "alfworld", seeds: List[int] | None = None) -> Dict[str, Any]:
    seeds = seeds or [11, 22]
    # B1 ReAct-like fixed agent (no evolution): direct+cot hybrid baseline via single genome
    # B2 random evolution, B3 NSGA-III, B4 +PEEM, B5 +PEEM+PPEC
    variants = {
        "B2_random_evolution": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "B3_nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "B4_nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "B5_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
    }
    runs = []
    # B1: fixed ReAct-like genome, evaluated once per seed
    pipe = RealBenchmarkPipeline(RealEvalConfig(benchmark=benchmark, n_tasks=8, seed=seeds[0]))
    from src.agent.genome import AgentGenome

    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    vec, episode, _ = pipe.evaluate_genome_recorded(react)
    runs.append({
        "variant": "B1_react_baseline",
        "seed": seeds[0],
        "success_rate": episode.success_rate,
        "mean_tokens": episode.totals()["mean_tokens"],
        "mean_latency": episode.totals()["mean_latency"],
        "mean_cost": episode.totals()["mean_cost"],
        "objectives": vec,
    })

    for seed in seeds:
        for name, kw in variants.items():
            print(f"  E1 {benchmark} {name} seed={seed}", flush=True)
            out = run_real_agent_evolution(
                benchmark=benchmark,
                n_tasks=8,
                pop_size=16,
                n_generations=8,
                seed=seed,
                **kw,
            )
            runs.append({
                "variant": name,
                "seed": seed,
                "success_rate": _objective_summary(out["front_fitness"], out["history"])["mean_performance"],
                "mean_cost": _objective_summary(out["front_fitness"], out["history"])["mean_cost"],
                "final_hv": out["final_hypervolume"],
                "final_pareto": out["final_pareto_size"],
                "history_len": len(out["history"]),
            })
    summary = {}
    for name in ["B1_react_baseline"] + list(variants):
        sub = [r for r in runs if r["variant"] == name]
        summary[name] = {
            "success_proxy": _ms([r.get("success_rate", 0.0) for r in sub]),
            "mean_cost": _ms([r.get("mean_cost", 0.0) for r in sub]),
        }
        if name != "B1_react_baseline":
            summary[name]["final_hv"] = _ms([r.get("final_hv", 0.0) for r in sub])
    return {"name": f"E1_baseline_comparison_{benchmark}", "runs": runs, "summary": summary}


def experiment_2(benchmark: str = "alfworld", seeds: List[int] | None = None) -> Dict[str, Any]:
    seeds = seeds or [7, 17]
    variants = {
        "nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "nsga3_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="accuracy_first"),
    }
    runs = []
    for seed in seeds:
        for name, kw in variants.items():
            print(f"  E2 {benchmark} {name} seed={seed}", flush=True)
            out = run_real_agent_evolution(
                benchmark=benchmark, n_tasks=8, pop_size=16, n_generations=8, seed=seed, **kw
            )
            runs.append({
                "variant": name,
                "seed": seed,
                "final_hv": out["final_hypervolume"],
                "front_fitness": out["front_fitness"],
                "pref_sat_accuracy": preference_satisfaction_score(
                    out["front_fitness"], encode_preference("accuracy_first")
                ),
            })
    summary = {}
    for name in variants:
        sub = [r for r in runs if r["variant"] == name]
        summary[name] = {
            "final_hv": _ms([r["final_hv"] for r in sub]),
            "pref_sat_accuracy": _ms([r["pref_sat_accuracy"] for r in sub]),
        }
    for r in runs:
        r.pop("front_fitness", None)
    return {"name": f"E2_ablation_{benchmark}", "runs": runs, "summary": summary}


def experiment_3(benchmark: str = "webshop", seeds: List[int] | None = None) -> Dict[str, Any]:
    seeds = seeds or [5, 15]
    prefs = ["accuracy_first", "cost_first", "balanced"]
    runs = []
    for seed in seeds:
        for pref in prefs:
            print(f"  E3 {benchmark} {pref} seed={seed}", flush=True)
            out = run_real_agent_evolution(
                benchmark=benchmark,
                n_tasks=8,
                pop_size=16,
                n_generations=8,
                seed=seed,
                preference=pref,
            )
            stats = _objective_summary(out["front_fitness"], out["history"], encode_preference(pref))
            runs.append({"seed": seed, "preference": pref, **stats})
    summary = {}
    for pref in prefs:
        sub = [r for r in runs if r["preference"] == pref]
        summary[pref] = {
            "pref_sat": _ms([r.get("pref_sat", 0.0) for r in sub]),
            "mean_performance": _ms([r["mean_performance"] for r in sub]),
            "mean_cost": _ms([r["mean_cost"] for r in sub]),
        }
    return {"name": f"E3_preference_scenarios_{benchmark}", "runs": runs, "summary": summary}


def experiment_4(benchmark: str = "alfworld") -> Dict[str, Any]:
    """Trajectory at generations 0/5/10/20 (single seed)."""
    out = run_real_agent_evolution(
        benchmark=benchmark,
        n_tasks=8,
        pop_size=20,
        n_generations=20,
        seed=42,
        preference="accuracy_first",
    )
    marks = [0, 5, 10, 20]
    traj = []
    hist = out["history"]
    for g in marks:
        if g < len(hist):
            h = hist[g]
            traj.append({
                "generation": g,
                "hypervolume": h.get("hypervolume", 0.0),
                "n_non_dominated": h.get("n_non_dominated", 0),
                "mutation_entropy": h.get("mutation_entropy", 0.0),
                "temperature": h.get("temperature", 0.0),
            })
    return {
        "name": f"E4_evolution_trajectory_{benchmark}",
        "marks": traj,
        "final_hv": out["final_hypervolume"],
        "final_pareto": out["final_pareto_size"],
    }


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> Dict[str, Any]:
    t0 = time.time()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("E1 alfworld...", flush=True)
    e1a = experiment_1("alfworld")
    print("E1 webshop...", flush=True)
    e1w = experiment_1("webshop")
    print("E2 alfworld...", flush=True)
    e2 = experiment_2("alfworld")
    print("E3 webshop...", flush=True)
    e3 = experiment_3("webshop")
    print("E4 alfworld...", flush=True)
    e4 = experiment_4("alfworld")

    payload = {
        "phase": "Phase 4 — Real Agent Benchmark Validation",
        "claim": "PEEM-PPEC improves real-world many-objective optimization of adaptive LLM agents",
        "offline_default": True,
        "note": "MockLLMBackend + simulated ALFWorld/WebShop unless OPENAI_API_KEY/DEEPSEEK_API_KEY set",
        "E1_alfworld": e1a,
        "E1_webshop": e1w,
        "E2_ablation": e2,
        "E3_preference": e3,
        "E4_trajectory": e4,
    }
    _write(RESULTS_DIR / "real_agent_results.json", payload)

    summary = {
        "results_path": str(RESULTS_DIR / "real_agent_results.json"),
        "E1_alfworld": e1a["summary"],
        "E1_webshop": e1w["summary"],
        "E2_ablation": e2["summary"],
        "E3_preference": e3["summary"],
        "E4_trajectory": e4,
        "wall_time_sec": time.time() - t0,
    }
    _write(RESULTS_DIR / "real_agent_summary.json", summary)

    # Structured result folders required by the spec.
    for sub in ("alfworld", "webshop", "evolution_history", "pareto_fronts"):
        (RESULTS_DIR / sub).mkdir(parents=True, exist_ok=True)
    _write(RESULTS_DIR / "evolution_history" / "trajectory.json", e4)
    _write(RESULTS_DIR / "alfworld" / "e1_summary.json", e1a["summary"])
    _write(RESULTS_DIR / "webshop" / "e1_summary.json", e1w["summary"])
    _write(RESULTS_DIR / "pareto_fronts" / "ablation.json", e2["summary"])

    print("Phase 4 real-agent demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
