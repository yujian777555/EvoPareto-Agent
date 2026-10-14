"""Phase 2 demo: Evolution Experience Memory vs random mutation.

Experiments
-----------
E1. Random mutation vs adaptive (HV + Pareto quality + convergence)
E2. Mutation efficiency: evaluations needed to reach HV target
E3. Ablation: NSGA-III vs NSGA-III + Evolution Memory

Usage:
    python experiments/run_evolution_memory_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import hypervolume
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.runtime.pipeline import build_default_pipeline

RESULTS_DIR = ROOT / "results"


def _run_once(use_adaptive: bool, *, pop_size: int, gens: int, seed: int, n_tasks: int) -> Dict[str, Any]:
    pipe = build_default_pipeline(n_tasks=n_tasks, seed=seed)
    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    loop.run(gens)
    return {
        "use_adaptive": use_adaptive,
        "seed": seed,
        "history": list(loop.history),
        "final_hv": loop.current_hypervolume(),
        "final_pareto": len(loop.pareto_front()),
        "evals": loop.generation * cfg.n_offspring + cfg.pop_size,
        "archive_size": len(loop.archive),
        "mutation_probs": loop.controller.probability_distribution(),
        "experience": loop.experience.summary(),
    }


def experiment_1(pop_size: int = 20, gens: int = 6, seeds: List[int] | None = None) -> Dict[str, Any]:
    seeds = seeds or [11, 22]
    rows = []
    for seed in seeds:
        rows.append(_run_once(False, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8))
        rows.append(_run_once(True, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8))
    def _avg(flag: bool, key: str) -> float:
        vals = [r[key] for r in rows if r["use_adaptive"] is flag]
        return sum(vals) / len(vals)
    return {
        "name": "E1_random_vs_adaptive",
        "runs": rows,
        "mean_final_hv_random": _avg(False, "final_hv"),
        "mean_final_hv_adaptive": _avg(True, "final_hv"),
        "mean_final_pareto_random": _avg(False, "final_pareto"),
        "mean_final_pareto_adaptive": _avg(True, "final_pareto"),
        "mean_hv_curve_random": _mean_curves([r["history"] for r in rows if not r["use_adaptive"]], "hypervolume"),
        "mean_hv_curve_adaptive": _mean_curves([r["history"] for r in rows if r["use_adaptive"]], "hypervolume"),
    }


def experiment_2(pop_size: int = 20, gens: int = 8, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Evaluations needed for adaptive vs random to reach random's final HV."""
    seeds = seeds or [7, 17]
    summary = []
    for seed in seeds:
        rnd = _run_once(False, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        adp = _run_once(True, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        target = rnd["final_hv"]
        summary.append(
            {
                "seed": seed,
                "target_hv": target,
                "evals_random_to_target": _evals_to_hv(rnd, target),
                "evals_adaptive_to_target": _evals_to_hv(adp, target),
                "evals_random_total": rnd["evals"],
                "evals_adaptive_total": adp["evals"],
            }
        )
    return {
        "name": "E2_mutation_efficiency",
        "records": summary,
        "mean_evals_random_to_target": _mean([s["evals_random_to_target"] for s in summary]),
        "mean_evals_adaptive_to_target": _mean([s["evals_adaptive_to_target"] for s in summary]),
    }


def experiment_3(pop_size: int = 20, gens: int = 6, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Ablation: adaptive controller with empty memory == random-like; full memory wins."""
    seeds = seeds or [5, 15]
    rows = []
    for seed in seeds:
        # Baseline NSGA-III + random mutation (no experience)
        base = _run_once(False, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        # Full method
        mem = _run_once(True, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        rows.append({"seed": seed, "nsga3_random": base, "nsga3_memory": mem})
    return {
        "name": "E3_ablation",
        "runs": rows,
        "mean_final_hv_nsga3": _mean([r["nsga3_random"]["final_hv"] for r in rows]),
        "mean_final_hv_nsga3_memory": _mean([r["nsga3_memory"]["final_hv"] for r in rows]),
        "mean_final_pareto_nsga3": _mean([r["nsga3_random"]["final_pareto"] for r in rows]),
        "mean_final_pareto_nsga3_memory": _mean([r["nsga3_memory"]["final_pareto"] for r in rows]),
        "mean_hv_curve_nsga3": _mean_curves([r["nsga3_random"]["history"] for r in rows], "hypervolume"),
        "mean_hv_curve_memory": _mean_curves([r["nsga3_memory"]["history"] for r in rows], "hypervolume"),
    }


def _evals_to_hv(run: Dict[str, Any], target: float) -> int:
    """Number of evaluation events when HV first reaches target (approx)."""
    pop = 20
    for h in run["history"]:
        if h["hypervolume"] >= target:
            return int(h["generation"]) * pop + pop
    return int(run["evals"])


def _mean(vals: List[float]) -> float:
    return float(sum(vals)) / float(len(vals)) if vals else 0.0


def _mean_curves(hists: List[List[Dict[str, Any]]], key: str) -> List[float]:
    if not hists:
        return []
    n = max(len(h) for h in hists)
    out = []
    for i in range(n):
        vals = [h[i][key] for h in hists if i < len(h)]
        out.append(_mean(vals))
    return out


def main() -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    e1 = experiment_1()
    e2 = experiment_2()
    e3 = experiment_3()

    payload = {
        "phase": "Phase 2 — Evolution Experience Memory",
        "objective": "optimizer memory (NOT agent memory / RAG / vector DB)",
        "E1": e1,
        "E2": e2,
        "E3": e3,
    }
    out_path = RESULTS_DIR / "evolution_memory_results.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    # Compact summary for humans
    summary = {
        "results_path": str(out_path),
        "E1_mean_final_hv_random": e1["mean_final_hv_random"],
        "E1_mean_final_hv_adaptive": e1["mean_final_hv_adaptive"],
        "E2_mean_evals_random_to_target": e2["mean_evals_random_to_target"],
        "E2_mean_evals_adaptive_to_target": e2["mean_evals_adaptive_to_target"],
        "E3_mean_final_hv_nsga3": e3["mean_final_hv_nsga3"],
        "E3_mean_final_hv_nsga3_memory": e3["mean_final_hv_nsga3_memory"],
    }
    summary_path = RESULTS_DIR / "evolution_memory_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Phase 2 evolution-memory demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
