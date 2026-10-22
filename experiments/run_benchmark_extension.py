"""Cross-benchmark extension experiments (Phase 5-Benchmark Extension).

Baseline matrix (all benchmarks, identical budget):
    B0 Random Search
    B1 ReAct
    B2 NSGA-II
    B3 NSGA-III
    B4 NSGA-III + PEEM
    B5 NSGA-III + PEEM + PPEC

Outputs under results/benchmark_extension/.
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.evaluation.metrics import (
    hypervolume,
    igd,
    preference_satisfaction_score,
    reference_front_from_population,
)
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.nsga2_baseline import NSGA2
from src.evolution.preference import encode_preference
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "benchmark_extension"

CONFIG = {
    "pop": 12,
    "gens": 8,
    "tasks": 10,
    "seeds": [11, 22, 33],
    "budget_evals": 12 * 9,  # 108 — identical for all methods
}


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


class NSGA2Loop(MemoryEvolutionLoop):
    """Same evolution loop, NSGA-II selector (baseline only)."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self.nsga3 = NSGA2(
            n_objectives=self.config.n_objectives,
            seed=self.config.seed,
        )


def run_method(
    method: str,
    *,
    benchmark: str,
    seed: int,
    use_adaptive: bool = True,
    experience_mode: str = "robust_peem",
    preference: Any = None,
    use_nsga2: bool = False,
    fixed_genome: Optional[AgentGenome] = None,
    track_curve: bool = False,
) -> Dict[str, Any]:
    cfg = CONFIG
    t0 = time.time()
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=cfg["tasks"], backend="mock", seed=seed, benchmark=benchmark),
        cache=None,
    )
    if hasattr(pipe.adapter, "max_workers"):
        pipe.adapter.max_workers = 4

    evaluation_rows: List[List[float]] = []

    def evaluate_and_record(genome: AgentGenome) -> List[float]:
        vec = list(pipe.evaluate_genome(genome))
        evaluation_rows.append(vec)
        return vec

    if fixed_genome is not None:
        agent = pipe.builder.build(fixed_genome, agent_id=0)
        ep, recs = pipe.adapter.run_recorded(agent)
        vec = pipe.objectives.from_episode(ep)
        return {
            "method": method, "benchmark": benchmark, "seed": seed,
            "objectives": vec, "success": vec[0], "cost": vec[2],
            "steps_proxy": 1.0 - vec[1],
            "wall_time": time.time() - t0, "curve": [],
            "population_rows": [vec],
        }

    mcfg = MemoryEvolutionConfig(
        pop_size=cfg["pop"], n_offspring=cfg["pop"], seed=seed,
        use_adaptive=use_adaptive, experience_mode=experience_mode,
        preference=preference,
    )
    loop_cls = NSGA2Loop if use_nsga2 else MemoryEvolutionLoop
    loop = loop_cls(evaluator=evaluate_and_record, config=mcfg)

    def archive_snapshot(generation: int) -> Dict[str, Any]:
        archive_front = reference_front_from_population(evaluation_rows)
        return {
            "generation": generation,
            "hypervolume": hypervolume(archive_front, n_samples=1024, seed=seed),
            "n_non_dominated": len(archive_front),
            "n_evaluations": len(evaluation_rows),
        }

    loop.initialize()
    curve = [archive_snapshot(0)]
    for _ in range(cfg["gens"]):
        loop.next_generation()
        curve.append(archive_snapshot(loop.generation))

    # Score every optimizer on the non-dominated archive of all candidates
    # evaluated under the same budget, not just its final surviving population.
    ff = reference_front_from_population(evaluation_rows)
    rows = ff
    pref = encode_preference(preference) if preference is not None else encode_preference("balanced")
    return {
        "method": method, "benchmark": benchmark, "seed": seed,
        "final_hv": hypervolume(ff, n_samples=1024, seed=seed),
        "final_pareto": len(ff),
        "success": sum(r[0] for r in rows) / len(rows) if rows else 0.0,
        "cost": sum(r[2] for r in rows) / len(rows) if rows else 0.0,
        "efficiency": sum(r[1] for r in rows) / len(rows) if rows else 0.0,
        "steps_proxy": sum(1.0 - r[1] for r in rows) / len(rows) if rows else 0.0,
        "pss": preference_satisfaction_score(rows, pref) if rows else 0.0,
        "front_rows": ff,
        "population_rows": rows,
        "curve": curve,
        "wall_time": time.time() - t0,
        "evaluations": len(evaluation_rows),
        "evaluation_protocol": "all_evaluated_candidates_pareto_archive",
    }


def run_random_search(*, benchmark: str, seed: int) -> Dict[str, Any]:
    """True random search: fresh random genomes, no parent selection or evolution.

    It uses the same number of candidate evaluations and the same generation-sized
    batches as the evolutionary methods. Metrics are computed on the Pareto
    archive of every evaluated candidate, using the same fixed HV reference.
    """
    cfg = CONFIG
    t0 = time.time()
    rng = random.Random(seed)
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=cfg["tasks"], backend="mock", seed=seed, benchmark=benchmark),
        cache=None,
    )
    if hasattr(pipe.adapter, "max_workers"):
        pipe.adapter.max_workers = 4

    evaluated_rows: List[List[float]] = []
    curve: List[Dict[str, Any]] = []
    for generation in range(cfg["gens"] + 1):
        for _ in range(cfg["pop"]):
            genome = AgentGenome.random(rng)
            evaluated_rows.append(list(pipe.evaluate_genome(genome)))
        archive_front = reference_front_from_population(evaluated_rows)
        curve.append({
            "generation": generation,
            "hypervolume": hypervolume(archive_front, n_samples=1024, seed=seed),
            "n_non_dominated": len(archive_front),
            "n_evaluations": len(evaluated_rows),
        })

    front = reference_front_from_population(evaluated_rows)
    pref = encode_preference("balanced")
    return {
        "method": "B0_random_search", "benchmark": benchmark, "seed": seed,
        "final_hv": hypervolume(front, n_samples=1024, seed=seed),
        "final_pareto": len(front),
        "success": sum(r[0] for r in front) / len(front) if front else 0.0,
        "cost": sum(r[2] for r in front) / len(front) if front else 0.0,
        "efficiency": sum(r[1] for r in front) / len(front) if front else 0.0,
        "steps_proxy": sum(1.0 - r[1] for r in front) / len(front) if front else 0.0,
        "pss": preference_satisfaction_score(front, pref) if front else 0.0,
        "front_rows": front,
        "population_rows": front,
        "curve": curve,
        "wall_time": time.time() - t0,
        "evaluations": len(evaluated_rows),
        "evaluation_protocol": "uniform_random_genomes_pareto_archive",
    }


METHODS = {
    "B2_nsga2": dict(use_adaptive=False, experience_mode="phase2", use_nsga2=True),
    "B3_nsga3": dict(use_adaptive=False, experience_mode="phase2"),
    "B4_nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem"),
    "B5_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
}


def run_benchmark(benchmark: str) -> Dict[str, Any]:
    print(f"=== {benchmark} ===", flush=True)
    runs = []
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    for seed in CONFIG["seeds"]:
        print(f"  B1_react seed={seed}", flush=True)
        runs.append(run_method(
            "B1_react", benchmark=benchmark, seed=seed,
            fixed_genome=react,
        ))
        print(f"  B0_random_search seed={seed}", flush=True)
        runs.append(run_random_search(benchmark=benchmark, seed=seed))
        for name, kw in METHODS.items():
            print(f"  {name} seed={seed}", flush=True)
            runs.append(run_method(name, benchmark=benchmark, seed=seed, **kw))

    # Shared IGD reference
    all_rows = []
    for r in runs:
        all_rows.extend(r.get("population_rows") or r.get("objectives") and [r["objectives"]] or [])
    ref = reference_front_from_population(all_rows) if all_rows else []
    for r in runs:
        front = r.get("front_rows") or ([r["objectives"]] if "objectives" in r else [])
        r["igd"] = igd(front, ref) if ref and front else 0.0

    table = []
    for name in ["B0_random_search", "B1_react", "B2_nsga2", "B3_nsga3", "B4_nsga3_peem", "B5_peem_ppec"]:
        sub = [r for r in runs if r["method"] == name]
        row = {
            "Method": name,
            "Success": _ms([r.get("success", 0.0) for r in sub]),
            "Cost": _ms([r.get("cost", 0.0) for r in sub]),
            "Steps": _ms([r.get("steps_proxy", 0.0) for r in sub]),
            "HV": _ms([r.get("final_hv", 0.0) for r in sub]),
            "IGD": _ms([r.get("igd", 0.0) for r in sub]),
            "PSS": _ms([r.get("pss", 0.0) for r in sub]),
        }
        table.append(row)
    # Strip bulky fields
    slim = []
    for r in runs:
        r2 = {k: v for k, v in r.items() if k not in ("front_rows", "population_rows")}
        slim.append(r2)
    return {"benchmark": benchmark, "config": CONFIG, "table": table, "runs": slim}


def figures_payload(alf: Dict, web: Dict) -> Dict[str, Any]:
    """Data for paper figures (rendered externally / matplotlib)."""
    # Fig1: Pareto (Success vs Cost) per method on WebShop
    fig1 = []
    for row in web["table"]:
        fig1.append({
            "method": row["Method"],
            "success": row["Success"]["mean"],
            "cost": row["Cost"]["mean"],
        })
    # Fig2: preference shift — from preference ablation style runs
    fig2 = []
    for pref in ("accuracy_first", "cost_first", "balanced"):
        r = run_method(
            f"PEEM_PPEC|{pref}", benchmark="webshop", seed=42, preference=pref,
        )
        rows = r.get("population_rows") or []
        if rows:
            fig2.append({
                "preference": pref,
                "mean_performance": sum(x[0] for x in rows) / len(rows),
                "mean_cost": sum(x[2] for x in rows) / len(rows),
                "pss": preference_satisfaction_score(rows, encode_preference(pref)),
            })
    # Fig3: evolution curves from B5 WebShop
    fig3 = []
    for r in web["runs"]:
        if r["method"] == "B5_peem_ppec" and r.get("curve"):
            fig3.append({"seed": r["seed"], "curve": [
                {"generation": h.get("generation"), "hypervolume": h.get("hypervolume")}
                for h in r["curve"]
            ]})
    return {"fig1_pareto": fig1, "fig2_preference_shift": fig2, "fig3_evolution": fig3}


def main() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    print("ALFWorld final...", flush=True)
    alf = run_benchmark("alfworld")
    _write(OUT / "alfworld_final.json", alf)
    print("WebShop final...", flush=True)
    web = run_benchmark("webshop")
    _write(OUT / "webshop_final.json", web)

    # NSGA-II vs III focused comparison
    nsga2_cmp = {
        "alfworld": [t for t in alf["table"] if t["Method"] in ("B2_nsga2", "B3_nsga3", "B4_nsga3_peem", "B5_peem_ppec")],
        "webshop": [t for t in web["table"] if t["Method"] in ("B2_nsga2", "B3_nsga3", "B4_nsga3_peem", "B5_peem_ppec")],
    }
    _write(OUT / "nsga2_comparison.json", nsga2_cmp)

    figs = figures_payload(alf, web)
    _write(OUT / "pareto_curves.json", figs)

    summary = {
        "config": CONFIG,
        "alfworld": alf["table"],
        "webshop": web["table"],
        "nsga2_comparison": nsga2_cmp,
        "figures": figs,
    }
    _write(OUT / "summary.json", summary)
    print("Benchmark extension complete.")
    print(json.dumps({"alfworld": alf["table"], "webshop": web["table"]}, indent=2)[:2000])
    return summary


if __name__ == "__main__":
    main()
