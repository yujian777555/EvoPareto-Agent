"""Phase 2.5-R1 demo: Robust PEEM vs baselines (E1–E4).

Baselines
---------
A. random mutation
B. success-rate adaptive (Phase 2)
C. PEEM v1 (Phase 2.5)
D. Robust PEEM (R1: rank credit + z-norm + delayed + temperature)

Usage:
    python experiments/run_robust_peem_demo.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
from src.runtime.pipeline import build_default_pipeline

RESULTS_DIR = ROOT / "results"


def _make_evaluator(n_tasks: int, seed: int, noise: float = 0.0):
    pipe = build_default_pipeline(n_tasks=n_tasks, seed=seed)
    base = pipe.as_evaluate_fn()

    if noise <= 0:
        return base

    def noisy(genome):
        vals = list(base(genome))
        # Deterministic noise from genome key + seed
        key = hash((genome.key(), seed)) & 0xFFFFFFFF
        rng = __import__("random").Random(key)
        return [
            min(1.0, max(0.0, v + rng.uniform(-noise, noise)))
            for v in vals
        ]

    return noisy


def _mode_flags(mode: str):
    if mode == "random":
        return False, "phase2", False, False
    if mode == "success":
        return True, "phase2", True, False
    if mode == "peem_v1":
        return True, "peem", True, False
    return True, "robust_peem", True, True  # robust


def _run(
    mode: str,
    *,
    pop_size: int,
    gens: int,
    seed: int,
    n_tasks: int = 6,
    noise: float = 0.0,
    use_softmax: bool = True,
    use_delayed: bool = True,
    experience_mode: Optional[str] = None,
) -> Dict[str, Any]:
    t0 = time.time()
    evaluator = _make_evaluator(n_tasks, seed, noise)
    use_adaptive, exp_mode, soft, delayed = _mode_flags(mode)
    if experience_mode:
        exp_mode = experience_mode
    if mode == "robust":
        soft = use_softmax
        delayed = use_delayed

    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=exp_mode,
        use_softmax=soft,
        use_delayed_credit=delayed,
    )
    loop = MemoryEvolutionLoop(evaluator=evaluator, config=cfg)
    loop.initialize()
    loop.run(gens)

    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    front = [list(i.fitness_vector or []) for i in loop.pareto_front()]
    counts = list(loop.mutation_type_counts().values())
    return {
        "mode": mode,
        "seed": seed,
        "noise": noise,
        "pop_size": pop_size,
        "gens": gens,
        "final_hv": hypervolume(rows, n_samples=1024, seed=seed),
        "final_pareto": len(front),
        "spacing": spacing(front) if front else 0.0,
        "mutation_entropy": mutation_entropy(counts) if counts else 0.0,
        "evals": pop_size * (gens + 1),
        "population_rows": rows,
        "front_rows": front,
        "history": loop.history,
        "wall_time": time.time() - t0,
    }


def _attach_igd(runs: List[Dict[str, Any]]) -> None:
    all_rows = []
    for r in runs:
        all_rows.extend(r.get("population_rows", []))
    ref = reference_front_from_population(all_rows)
    for r in runs:
        front = r.get("front_rows") or []
        r["igd"] = igd(front, ref) if ref else 0.0


def _strip_rows(runs: List[Dict[str, Any]]) -> None:
    for r in runs:
        r.pop("population_rows", None)
        r.pop("front_rows", None)


def _mean_std(vals: List[float]) -> Dict[str, float]:
    n = len(vals)
    if n == 0:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / n
    return {"mean": m, "std": var ** 0.5}


def experiment_1(pop_size: int = 50, gens: int = 25, seeds: List[int] | None = None) -> Dict[str, Any]:
    seeds = seeds or [11, 22, 33, 44, 55]
    modes = ("random", "success", "peem_v1", "robust")
    runs = []
    for seed in seeds:
        for mode in modes:
            print(f"  E1 {mode} seed={seed}", flush=True)
            runs.append(_run(mode, pop_size=pop_size, gens=gens, seed=seed))
    _attach_igd(runs)
    out = {
        "name": "E1_mutation_strategy_comparison",
        "config": {"pop_size": pop_size, "gens": gens, "seeds": seeds},
        "runs": [],
        "summary": {},
    }
    for mode in modes:
        sub = [r for r in runs if r["mode"] == mode]
        out["summary"][mode] = {
            "final_hv": _mean_std([r["final_hv"] for r in sub]),
            "igd": _mean_std([r["igd"] for r in sub]),
            "spacing": _mean_std([r["spacing"] for r in sub]),
            "mutation_entropy": _mean_std([r["mutation_entropy"] for r in sub]),
        }
        for r in sub:
            rr = dict(r)
            rr.pop("population_rows", None)
            rr.pop("front_rows", None)
            out["runs"].append(rr)
    return out


def experiment_2(e1: Dict[str, Any], pop_size: int = 50) -> Dict[str, Any]:
    """Search efficiency: evals to reach random's mean final HV."""
    target = e1["summary"]["random"]["final_hv"]["mean"]
    recs = []
    for r in e1["runs"]:
        if r.get("final_hv", 0) >= target:
            # first generation HV in history
            budget = pop_size
            for h in r.get("history", []):
                if h.get("hypervolume", 0) >= target:
                    budget = int(h["generation"]) * pop_size + pop_size
                    break
            recs.append({"mode": r["mode"], "seed": r["seed"], "evals_to_target": budget})
        else:
            recs.append({"mode": r["mode"], "seed": r["seed"], "evals_to_target": r["evals"]})
    summary = {}
    for mode in ("random", "success", "peem_v1", "robust"):
        vals = [x["evals_to_target"] for x in recs if x["mode"] == mode]
        summary[mode] = _mean_std([float(v) for v in vals])
    return {"name": "E2_search_efficiency", "target_hv": target, "records": recs, "summary": summary}


def experiment_3(pop_size: int = 50, gens: int = 25, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Ablation: remove Pareto credit / diversity / delayed / temperature."""
    seeds = seeds or [7, 17, 27, 37, 47]
    variants = {
        "full_robust": dict(use_softmax=True, use_delayed=True, experience_mode="robust_peem"),
        "no_pareto_bucket": dict(use_softmax=True, use_delayed=True, experience_mode="peem"),  # v1 HV path
        "no_delayed": dict(use_softmax=True, use_delayed=False, experience_mode="robust_peem"),
        "no_temperature": dict(use_softmax=False, use_delayed=True, experience_mode="robust_peem"),
    }
    rows = []
    for seed in seeds:
        for name, kw in variants.items():
            print(f"  E3 {name} seed={seed}", flush=True)
            r = _run("robust", pop_size=pop_size, gens=gens, seed=seed, **kw)
            r["variant"] = name
            rows.append(r)
    summary = {}
    for name in variants:
        vals = [r["final_hv"] for r in rows if r["variant"] == name]
        summary[name] = _mean_std(vals)
    _strip_rows(rows)
    return {"name": "E3_credit_ablation", "config": {"pop_size": pop_size, "gens": gens, "seeds": seeds}, "runs": rows, "summary": summary}


def experiment_4(pop_size: int = 50, gens: int = 20, seeds: List[int] | None = None) -> Dict[str, Any]:
    """Noise robustness at 5% / 10% / 20%."""
    seeds = seeds or [3, 13, 23]
    noises = [0.05, 0.10, 0.20]
    rows = []
    for seed in seeds:
        for noise in noises:
            for mode in ("success", "peem_v1", "robust"):
                print(f"  E4 {mode} noise={noise} seed={seed}", flush=True)
                r = _run(mode, pop_size=pop_size, gens=gens, seed=seed, noise=noise)
                rows.append(r)
    summary: Dict[str, Any] = {}
    for noise in noises:
        summary[f"noise_{int(noise*100)}"] = {}
        for mode in ("success", "peem_v1", "robust"):
            vals = [r["final_hv"] for r in rows if r["mode"] == mode and abs(r["noise"] - noise) < 1e-9]
            summary[f"noise_{int(noise*100)}"][mode] = _mean_std(vals)
    _strip_rows(rows)
    return {"name": "E4_noise_robustness", "config": {"pop_size": pop_size, "gens": gens, "seeds": seeds}, "runs": rows, "summary": summary}


def main() -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / "robust_peem_results.json"
    summary_path = RESULTS_DIR / "robust_peem_summary.json"

    print("E1...", flush=True)
    e1 = experiment_1()
    _write_json(out_path, {"phase": "Phase 2.5-R1", "E1": e1})
    print("E2...", flush=True)
    e2 = experiment_2(e1)
    _write_json(out_path, {"phase": "Phase 2.5-R1", "E1": e1, "E2": e2})
    print("E3...", flush=True)
    e3 = experiment_3()
    _write_json(out_path, {"phase": "Phase 2.5-R1", "E1": e1, "E2": e2, "E3": e3})
    print("E4...", flush=True)
    e4 = experiment_4()

    payload = {
        "phase": "Phase 2.5-R1 — Robust PEEM",
        "claim": "rank-based Pareto credit + z-normalization + delayed credit + temperature softmax",
        "E1": e1,
        "E2": e2,
        "E3": e3,
        "E4": e4,
    }
    _write_json(out_path, payload)

    summary = {
        "results_path": str(out_path),
        "E1_final_hv": {m: e1["summary"][m]["final_hv"] for m in e1["summary"]},
        "E1_igd": {m: e1["summary"][m]["igd"] for m in e1["summary"]},
        "E2_evals_to_target": e2["summary"],
        "E3_ablation_hv": e3["summary"],
        "E4_noise_hv": e4["summary"],
    }
    _write_json(summary_path, summary)

    print("Phase 2.5-R1 Robust PEEM demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def _write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
