"""Phase 2.5 demo: PEEM vs baselines (E1–E4).

Baselines
---------
A. random mutation
B. Phase 2 success-rate adaptive mutation
C. PEEM (Pareto-aware Evolution Experience Memory)

Usage:
    python experiments/run_peem_demo.py
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

from src.evaluation.metrics import (
    hypervolume,
    igd,
    mutation_entropy,
    reference_front_from_population,
    spacing,
)
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.credit_assignment import CreditWeights
from src.runtime.pipeline import build_default_pipeline

RESULTS_DIR = ROOT / "results"


def _run(mode: str, *, pop_size: int, gens: int, seed: int, n_tasks: int, decay: float = 0.35,
         weights: CreditWeights | None = None, ref_front: List[List[float]] | None = None) -> Dict[str, Any]:
    t0 = time.time()
    pipe = build_default_pipeline(n_tasks=n_tasks, seed=seed)
    if mode == "random":
        use_adaptive, exp_mode = False, "phase2"
    elif mode == "success":
        use_adaptive, exp_mode = True, "phase2"
    else:
        use_adaptive, exp_mode = True, "peem"

    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=exp_mode,
        decay=decay,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    if weights is not None and exp_mode == "peem":
        loop.experience.config.weights = weights  # type: ignore[union-attr]
    loop.initialize()
    loop.run(gens)

    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    front = [list(i.fitness_vector or []) for i in loop.pareto_front()]
    hv = hypervolume(rows, n_samples=2048, seed=seed)
    counts = list(loop.mutation_type_counts().values())
    return {
        "mode": mode,
        "seed": seed,
        "final_hv": hv,
        "final_pareto": len(front),
        "population_rows": rows,
        "front_rows": front,
        "spacing": spacing(front) if front else 0.0,
        "mutation_entropy": mutation_entropy(counts) if counts else 0.0,
        "evals": pop_size * (gens + 1),
        "history": loop.history,
        "mutation_probs": loop.controller.probability_distribution(),
        "wall_time": time.time() - t0,
    }


def _attach_igd(runs: List[Dict[str, Any]]) -> None:
    """Reference front = mixed non-dominated union of all runs' populations."""
    all_rows = []
    for r in runs:
        all_rows.extend(r.get("population_rows", []))
    ref = reference_front_from_population(all_rows)
    for r in runs:
        front = r.get("front_rows") or []
        r["igd"] = igd(front, ref) if ref else 0.0


def experiment_1(pop_size: int = 30, gens: int = 12, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Mutation strategy comparison: random vs success-rate vs PEEM."""
    seeds = seeds or [11, 22]
    runs = []
    for seed in seeds:
        for mode in ("random", "success", "peem"):
            runs.append(_run(mode, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8))
    _attach_igd(runs)

    def avg(mode: str, key: str) -> float:
        vals = [r[key] for r in runs if r["mode"] == mode]
        return sum(vals) / len(vals) if vals else 0.0

    # Strip bulky rows before persisting.
    for r in runs:
        r.pop("population_rows", None)
        r.pop("front_rows", None)

    return {
        "name": "E1_mutation_strategy_comparison",
        "runs": runs,
        "mean_final_hv": {m: avg(m, "final_hv") for m in ("random", "success", "peem")},
        "mean_igd": {m: avg(m, "igd") for m in ("random", "success", "peem")},
        "mean_spacing": {m: avg(m, "spacing") for m in ("random", "success", "peem")},
        "mean_entropy": {m: avg(m, "mutation_entropy") for m in ("random", "success", "peem")},
    }


def experiment_2(pop_size: int = 30, gens: int = 12, seeds: List[int] | None = None) -> Dict[str, Any]:
    """NSGA-III vs NSGA-III+SuccessMemory vs NSGA-III+PEEM."""
    seeds = seeds or [7, 17]
    runs = []
    for seed in seeds:
        for mode in ("random", "success", "peem"):
            runs.append(_run(mode, pop_size=pop_size, gens=gens, seed=seed, n_tasks=8))
    _attach_igd(runs)

    def avg(mode: str, key: str) -> float:
        vals = [r[key] for r in runs if r["mode"] == mode]
        return sum(vals) / len(vals) if vals else 0.0

    for r in runs:
        r.pop("population_rows", None)
        r.pop("front_rows", None)

    return {
        "name": "E2_nsga3_enhancement",
        "runs": runs,
        "mean_final_hv": {m: avg(m, "final_hv") for m in ("random", "success", "peem")},
        "mean_igd": {m: avg(m, "igd") for m in ("random", "success", "peem")},
        "mean_final_pareto": {m: avg(m, "final_pareto") for m in ("random", "success", "peem")},
        "mean_hv_curve": {
            m: _mean_curves([r["history"] for r in runs if r["mode"] == m], "hypervolume")
            for m in ("random", "success", "peem")
        },
    }


def experiment_3(pop_size: int = 30, gens: int = 12, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Evaluations to reach random's final HV (search efficiency)."""
    seeds = seeds or [5, 15]
    recs = []
    for seed in seeds:
        rnd = _run("random", pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        suc = _run("success", pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        peem = _run("peem", pop_size=pop_size, gens=gens, seed=seed, n_tasks=8)
        target = rnd["final_hv"]
        recs.append({
            "seed": seed,
            "target_hv": target,
            "evals_random": _evals_to_hv(rnd, target, pop_size),
            "evals_success": _evals_to_hv(suc, target, pop_size),
            "evals_peem": _evals_to_hv(peem, target, pop_size),
            "final_hv_peem": peem["final_hv"],
        })
    return {
        "name": "E3_search_efficiency",
        "records": recs,
        "mean_evals": {
            "random": sum(r["evals_random"] for r in recs) / len(recs),
            "success": sum(r["evals_success"] for r in recs) / len(recs),
            "peem": sum(r["evals_peem"] for r in recs) / len(recs),
        },
    }


def experiment_4(pop_size: int = 24, gens: int = 10, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Ablation: remove HV / diversity / survival credit components."""
    seeds = seeds or [3, 13]
    variants = {
        "full": CreditWeights(0.35, 0.30, 0.20, 0.15),
        "no_hv": CreditWeights(0.55, 0.0, 0.25, 0.20),
        "no_div": CreditWeights(0.50, 0.35, 0.0, 0.15),
        "no_surv": CreditWeights(0.45, 0.35, 0.20, 0.0),
    }
    rows = []
    for seed in seeds:
        for name, w in variants.items():
            r = _run("peem", pop_size=pop_size, gens=gens, seed=seed, n_tasks=8, weights=w)
            r["variant"] = name
            rows.append(r)
    summary = {}
    for name in variants:
        vals = [r["final_hv"] for r in rows if r["variant"] == name]
        summary[name] = sum(vals) / len(vals) if vals else 0.0
    return {"name": "E4_ablation", "runs": rows, "mean_final_hv": summary}


def _evals_to_hv(run: Dict[str, Any], target: float, pop: int) -> int:
    for h in run["history"]:
        if h.get("hypervolume", 0) >= target:
            return int(h["generation"]) * pop + pop
    return int(run["evals"])


def _mean_curves(hists: List[List[Dict[str, Any]]], key: str) -> List[float]:
    if not hists:
        return []
    n = max(len(h) for h in hists)
    out = []
    for i in range(n):
        vals = [h[i][key] for h in hists if i < len(h) and key in h[i]]
        out.append(sum(vals) / len(vals) if vals else 0.0)
    return out


def main() -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    e1 = experiment_1()
    e2 = experiment_2()
    e3 = experiment_3()
    e4 = experiment_4()

    payload = {
        "phase": "Phase 2.5 — Pareto-aware Evolution Experience Memory (PEEM)",
        "claim": "PEEM estimates mutation utility from Pareto improvement, diversity, and survival feedback",
        "E1": e1,
        "E2": e2,
        "E3": e3,
        "E4": e4,
    }
    out_path = RESULTS_DIR / "peem_results.json"
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "results_path": str(out_path),
        "E1_mean_final_hv": e1["mean_final_hv"],
        "E1_mean_igd": e1["mean_igd"],
        "E2_mean_final_hv": e2["mean_final_hv"],
        "E3_mean_evals": e3["mean_evals"],
        "E4_mean_final_hv": e4["mean_final_hv"],
    }
    summary_path = RESULTS_DIR / "peem_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Phase 2.5 PEEM demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
