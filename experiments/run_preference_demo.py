"""Phase 3 demo: Preference-aware Pareto Evolution Controller (PPEC).

E1 Preference adaptation: fixed NSGA-III vs preference-aware
E2 Pareto region selection: different prefs -> different regions
E3 NSGA-III vs +PEEM vs +PEEM+Preference
E4 Preference robustness (preference noise 5/10/20%)

Usage:
    python experiments/run_preference_demo.py
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
    preference_satisfaction_score,
    reference_front_from_population,
    spacing,
)
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.preference import encode_preference
from src.runtime.pipeline import build_default_pipeline

RESULTS_DIR = ROOT / "results"


def _run(
    *,
    mode: str = "robust",
    preference: Any = None,
    pop_size: int = 30,
    gens: int = 20,
    seed: int = 0,
    n_tasks: int = 6,
    use_adaptive: bool = True,
    experience_mode: str = "robust_peem",
    pref_noise: float = 0.0,
) -> Dict[str, Any]:
    t0 = time.time()
    pipe = build_default_pipeline(n_tasks=n_tasks, seed=seed)
    evaluator = pipe.as_evaluate_fn()

    pref = preference
    if pref is not None and pref_noise > 0:
        base = encode_preference(pref).as_tuple()
        import random as _r

        rng = _r.Random(seed * 17 + int(pref_noise * 100))
        pref = [min(1.0, max(0.0, v + rng.uniform(-pref_noise, pref_noise))) for v in base]

    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=experience_mode,
        preference=pref,
    )
    loop = MemoryEvolutionLoop(evaluator=evaluator, config=cfg)
    loop.initialize()
    loop.run(gens)

    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    front = [list(i.fitness_vector or []) for i in loop.pareto_front()]
    pref_obj = encode_preference(pref) if pref is not None else encode_preference("balanced")
    counts = list(loop.mutation_type_counts().values())
    return {
        "seed": seed,
        "preference": pref_obj.as_dict(),
        "preference_arg": pref if not isinstance(pref, list) else list(pref),
        "final_hv": hypervolume(rows, n_samples=512, seed=seed),
        "final_pareto": len(front),
        "spacing": spacing(front) if front else 0.0,
        "pref_sat": preference_satisfaction_score(rows, pref_obj),
        "pref_sat_front": preference_satisfaction_score(front, pref_obj) if front else 0.0,
        "mean_performance": sum(r[0] for r in rows) / len(rows),
        "mean_cost": sum(r[2] for r in rows) / len(rows),
        "mean_efficiency": sum(r[1] for r in rows) / len(rows),
        "mean_robustness": sum(r[3] for r in rows) / len(rows),
        "mutation_entropy": mutation_entropy(counts) if counts else 0.0,
        "population_rows": rows,
        "front_rows": front,
        "wall_time": time.time() - t0,
        "history": loop.history,
    }


def _ms(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    if not n:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    return {"mean": m, "std": var ** 0.5}


def _strip(runs: List[Dict[str, Any]]) -> None:
    for r in runs:
        r.pop("population_rows", None)
        r.pop("front_rows", None)


def experiment_1(pop_size: int = 30, gens: int = 20, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Fixed NSGA-III (no pref) vs preference-aware, under different task prefs."""
    seeds = seeds or [11, 22, 33]
    modes = ["accuracy_first", "cost_first", "balanced"]
    runs = []
    for seed in seeds:
        for mode in modes:
            runs.append(_run(preference=mode, pop_size=pop_size, gens=gens, seed=seed))
            runs.append(_run(preference=None, pop_size=pop_size, gens=gens, seed=seed))
    summary = {}
    for mode in modes:
        pref_runs = [r for r in runs if r["preference_arg"] == mode]
        null_runs = [r for r in runs if r["preference_arg"] is None]
        summary[mode] = {
            "pref_aware_sat": _ms([r["pref_sat"] for r in pref_runs]),
            "fixed_sat": _ms([
                preference_satisfaction_score(
                    r.get("population_rows", []) or [],
                    encode_preference(mode),
                )
                for r in null_runs
            ]),
            "pref_aware_perf": _ms([r["mean_performance"] for r in pref_runs]),
            "pref_aware_cost": _ms([r["mean_cost"] for r in pref_runs]),
        }
    _strip(runs)
    return {"name": "E1_preference_adaptation", "runs": runs, "summary": summary}


def experiment_2(pop_size: int = 30, gens: int = 20, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Different preferences should produce different Pareto regions."""
    seeds = seeds or [5, 15, 25]
    modes = ["accuracy_first", "cost_first", "robust_first", "balanced"]
    runs = []
    for seed in seeds:
        for mode in modes:
            runs.append(_run(preference=mode, pop_size=pop_size, gens=gens, seed=seed))
    summary = {}
    for mode in modes:
        sub = [r for r in runs if r["preference_arg"] == mode]
        summary[mode] = {
            "pref_sat": _ms([r["pref_sat"] for r in sub]),
            "mean_performance": _ms([r["mean_performance"] for r in sub]),
            "mean_cost": _ms([r["mean_cost"] for r in sub]),
            "mean_efficiency": _ms([r["mean_efficiency"] for r in sub]),
            "mean_robustness": _ms([r["mean_robustness"] for r in sub]),
        }
    _strip(runs)
    return {"name": "E2_pareto_region_selection", "runs": runs, "summary": summary}


def experiment_3(pop_size: int = 30, gens: int = 20, seeds: List[int] | None = None) -> Dict[str, Any]:
    """NSGA-III vs +PEEM vs +PEEM+Preference under accuracy_first."""
    seeds = seeds or [7, 17, 27]
    variants = {
        "nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "nsga3_peem_pref": dict(use_adaptive=True, experience_mode="robust_peem", preference="accuracy_first"),
    }
    runs = []
    for seed in seeds:
        for name, kw in variants.items():
            r = _run(pop_size=pop_size, gens=gens, seed=seed, **kw)
            r["variant"] = name
            runs.append(r)
    summary = {}
    for name in variants:
        sub = [r for r in runs if r["variant"] == name]
        summary[name] = {
            "final_hv": _ms([r["final_hv"] for r in sub]),
            "pref_sat_accuracy": _ms([
                preference_satisfaction_score(
                    r.get("population_rows", []) or [], encode_preference("accuracy_first")
                )
                for r in sub
            ]),
            "mean_performance": _ms([r["mean_performance"] for r in sub]),
        }
    _strip(runs)
    return {"name": "E3_module_contribution", "runs": runs, "summary": summary}


def experiment_4(pop_size: int = 30, gens: int = 15, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Preference noise robustness."""
    seeds = seeds or [3, 13, 23]
    noises = [0.05, 0.10, 0.20]
    runs = []
    for seed in seeds:
        for noise in noises:
            r = _run(
                preference="accuracy_first",
                pop_size=pop_size,
                gens=gens,
                seed=seed,
                pref_noise=noise,
            )
            r["pref_noise"] = noise
            runs.append(r)
    summary = {}
    for noise in noises:
        sub = [r for r in runs if abs(r["pref_noise"] - noise) < 1e-9]
        summary[f"noise_{int(noise*100)}"] = {
            "pref_sat": _ms([r["pref_sat"] for r in sub]),
            "final_hv": _ms([r["final_hv"] for r in sub]),
        }
    _strip(runs)
    return {"name": "E4_preference_robustness", "runs": runs, "summary": summary}


def _write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "preference_results.json"
    summary_path = RESULTS_DIR / "preference_summary.json"

    print("E1...", flush=True)
    e1 = experiment_1()
    _write(out_path, {"phase": "Phase 3", "E1": e1})
    print("E2...", flush=True)
    e2 = experiment_2()
    _write(out_path, {"phase": "Phase 3", "E1": e1, "E2": e2})
    print("E3...", flush=True)
    e3 = experiment_3()
    _write(out_path, {"phase": "Phase 3", "E1": e1, "E2": e2, "E3": e3})
    print("E4...", flush=True)
    e4 = experiment_4()

    payload = {
        "phase": "Phase 3 — Preference-aware Pareto Evolution Controller (PPEC)",
        "claim": "preference-conditioned evolutionary optimization guides NSGA-III to task-specific Pareto regions",
        "E1": e1,
        "E2": e2,
        "E3": e3,
        "E4": e4,
    }
    _write(out_path, payload)

    summary = {
        "results_path": str(out_path),
        "E1": e1["summary"],
        "E2": e2["summary"],
        "E3": e3["summary"],
        "E4": e4["summary"],
    }
    _write(summary_path, summary)
    print("Phase 3 preference demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
