"""Phase 4-R2: Final real-LLM experiment freeze (evidence only).

No algorithm changes. Records episode-level JSON, cache stats, cost.

Default scale is REDUCED from the paper target because of DeepSeek latency
(~6s/call). Reduction is recorded in cost_report.json / the doc.

Usage:
    python experiments/run_final_real_llm.py --scale reduced
    python experiments/run_final_real_llm.py --scale paper   # long
    python experiments/run_final_real_llm.py --scale mock    # offline check
"""

from __future__ import annotations

import argparse
import json
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
    mutation_entropy,
    preference_satisfaction_score,
    reference_front_from_population,
)
from src.evolution.preference import encode_preference
from src.runtime.cache import EvaluationCache
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "final_real_llm"

# Paper target vs shipped reduction (latency bound).
SCALES = {
    "paper": dict(pop=16, gens=10, tasks=50, seeds=[11, 22, 33], workers=8),
    "reduced": dict(pop=8, gens=6, tasks=8, seeds=[11], workers=6),
    "micro": dict(pop=5, gens=2, tasks=3, seeds=[11], workers=4),
    "mock": dict(pop=10, gens=6, tasks=10, seeds=[11, 22], workers=4),
}


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


def _episode_rows(
    *,
    method: str,
    seed: int,
    generation: int,
    genome: AgentGenome,
    task_id: str,
    success: bool,
    steps: int,
    tokens: int,
    latency: float,
    cost: float,
    trajectory: List[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "seed": seed,
        "method": method,
        "generation": generation,
        "genome": genome.to_dict(),
        "success": bool(success),
        "steps": int(steps),
        "tokens": int(tokens),
        "latency": float(latency),
        "cost": float(cost),
        "trajectory": list(trajectory),
    }


def run_method(
    method: str,
    *,
    backend: str,
    cfg: Dict[str, Any],
    seed: int,
    preference: Any = None,
    use_adaptive: bool = True,
    experience_mode: str = "robust_peem",
    fixed_genome: Optional[AgentGenome] = None,
    cache_path: Path,
    log_episodes: bool = True,
) -> Dict[str, Any]:
    t0 = time.time()
    cache = EvaluationCache(cache_path)
    pipe = RealLLMPipeline(
        RealLLMConfig(
            n_tasks=cfg["tasks"],
            backend=backend,
            seed=seed,
            preference=preference,
            cache_path=str(cache_path),
        ),
        cache=cache,
    )
    # Wire parallel workers into adapter (evaluation infra only).
    if hasattr(pipe.adapter, "max_workers"):
        pipe.adapter.max_workers = cfg.get("workers", 4)

    episodes: List[Dict[str, Any]] = []

    if fixed_genome is not None:
        # B1 ReAct: single genome, no evolution.
        agent = pipe.builder.build(fixed_genome, agent_id=0)
        ep, recs = pipe.adapter.run_recorded(agent)
        vec = pipe.objectives.from_episode(ep)
        if log_episodes:
            for r in recs:
                episodes.append(_episode_rows(
                    method=method, seed=seed, generation=0, genome=fixed_genome,
                    task_id=r.task_id, success=r.success, steps=r.steps,
                    tokens=r.tokens, latency=r.latency, cost=r.cost,
                    trajectory=r.trajectory,
                ))
        summary = {
            "method": method,
            "seed": seed,
            "objectives": vec,
            "success": vec[0],
            "efficiency": vec[1],
            "cost": vec[2],
            "robustness": vec[3],
            "autonomy": vec[4],
            "wall_time": time.time() - t0,
            "cost_report": pipe.cost_report(),
            "episodes": episodes,
        }
        return summary

    from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop

    mcfg = MemoryEvolutionConfig(
        pop_size=cfg["pop"],
        n_offspring=cfg["pop"],
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=experience_mode,
        preference=preference,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=mcfg)
    loop.initialize()

    # Log generation 0 episodes.
    if log_episodes:
        for ind in loop.individuals:
            _, _, recs = pipe.evaluate_genome_recorded(ind.genome)
            for r in recs:
                episodes.append(_episode_rows(
                    method=method, seed=seed, generation=0, genome=ind.genome,
                    task_id=r.task_id, success=r.success, steps=r.steps,
                    tokens=r.tokens, latency=r.latency, cost=r.cost,
                    trajectory=r.trajectory,
                ))

    for gen in range(cfg["gens"]):
        loop.next_generation()
        if log_episodes and gen in (0, cfg["gens"] // 2, cfg["gens"] - 1):
            for ind in loop.individuals:
                _, _, recs = pipe.evaluate_genome_recorded(ind.genome)
                for r in recs:
                    episodes.append(_episode_rows(
                        method=method, seed=seed, generation=gen + 1, genome=ind.genome,
                        task_id=r.task_id, success=r.success, steps=r.steps,
                        tokens=r.tokens, latency=r.latency, cost=r.cost,
                        trajectory=r.trajectory,
                    ))

    front = loop.pareto_front()
    ff = [list(i.fitness_vector or []) for i in front]
    return {
        "method": method,
        "seed": seed,
        "final_hv": loop.current_hypervolume(),
        "final_pareto": len(front),
        "front_fitness": ff,
        "success": sum(r[0] for r in ff) / len(ff) if ff else 0.0,
        "cost": sum(r[2] for r in ff) / len(ff) if ff else 0.0,
        "efficiency": sum(r[1] for r in ff) / len(ff) if ff else 0.0,
        "history": loop.history,
        "wall_time": time.time() - t0,
        "cost_report": pipe.cost_report(),
        "episodes": episodes,
    }


def experiment_overall(backend: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    print("E1 overall...", flush=True)
    rows = []
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    for seed in cfg["seeds"]:
        print(f"  B1_react seed={seed}", flush=True)
        rows.append(run_method(
            "B1_react", backend=backend, cfg=cfg, seed=seed,
            fixed_genome=react, cache_path=OUT / "cache_overall.json",
        ))
        for name, kw in [
            ("B0_random_search", dict(use_adaptive=False, experience_mode="phase2")),
            ("B2_nsga3", dict(use_adaptive=False, experience_mode="phase2")),
            ("B3_nsga3_peem", dict(use_adaptive=True, experience_mode="robust_peem")),
            ("B4_peem_ppec", dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced")),
        ]:
            print(f"  {name} seed={seed}", flush=True)
            rows.append(run_method(
                name, backend=backend, cfg=cfg, seed=seed,
                cache_path=OUT / "cache_overall.json", **kw
            ))
    # IGD vs union reference
    all_rows = []
    for r in rows:
        all_rows.extend(r.get("front_fitness") or ([r["objectives"]] if "objectives" in r else []))
    ref = reference_front_from_population(all_rows) if all_rows else []
    for r in rows:
        front = r.get("front_fitness") or ([r["objectives"]] if "objectives" in r else [])
        r["igd"] = igd(front, ref) if ref and front else 0.0
        r.pop("episodes", None)  # stored separately
        r.pop("history", None)

    summary = {}
    for name in ["B0_random_search", "B1_react", "B2_nsga3", "B3_nsga3_peem", "B4_peem_ppec"]:
        sub = [r for r in rows if r["method"] == name]
        summary[name] = {
            "success": _ms([r.get("success", 0.0) for r in sub]),
            "cost": _ms([r.get("cost", 0.0) for r in sub]),
            "efficiency": _ms([r.get("efficiency", 0.0) for r in sub]),
            "tokens_proxy": _ms([1.0 - r.get("efficiency", 0.0) for r in sub]),
            "igd": _ms([r.get("igd", 0.0) for r in sub]),
        }
        if name not in ("B1_react",):
            summary[name]["final_hv"] = _ms([r.get("final_hv", 0.0) for r in sub])
    return {"rows": rows, "summary": summary}


def experiment_ablation(backend: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    print("E2 ablation...", flush=True)
    variants = {
        "nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "nsga3_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="accuracy_first"),
    }
    rows = []
    for seed in cfg["seeds"]:
        for name, kw in variants.items():
            print(f"  {name} seed={seed}", flush=True)
            r = run_method(name, backend=backend, cfg=cfg, seed=seed,
                           cache_path=OUT / "cache_ablation.json", **kw)
            ff = r.get("front_fitness") or []
            r["pss_accuracy"] = preference_satisfaction_score(ff, encode_preference("accuracy_first")) if ff else 0.0
            r.pop("episodes", None)
            r.pop("history", None)
            rows.append(r)
    summary = {}
    for name in variants:
        sub = [r for r in rows if r["method"] == name]
        summary[name] = {
            "final_hv": _ms([r.get("final_hv", 0.0) for r in sub]),
            "success": _ms([r.get("success", 0.0) for r in sub]),
            "pss_accuracy": _ms([r.get("pss_accuracy", 0.0) for r in sub]),
        }
    return {"rows": rows, "summary": summary}


def experiment_preference(backend: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    print("E3 preference...", flush=True)
    prefs = ["accuracy_first", "cost_first", "balanced"]
    rows = []
    for seed in cfg["seeds"]:
        for pref in prefs:
            print(f"  {pref} seed={seed}", flush=True)
            r = run_method(
                f"pref_{pref}", backend=backend, cfg=cfg, seed=seed,
                preference=pref, cache_path=OUT / "cache_pref.json",
            )
            ff = r.get("front_fitness") or []
            r["pss"] = preference_satisfaction_score(ff, encode_preference(pref)) if ff else 0.0
            r.pop("episodes", None)
            r.pop("history", None)
            rows.append({"preference": pref, **{k: r[k] for k in
                        ("seed", "success", "cost", "final_hv", "pss", "wall_time") if k in r}})
    summary = {}
    for pref in prefs:
        sub = [r for r in rows if r["preference"] == pref]
        summary[pref] = {
            "success": _ms([r.get("success", 0.0) for r in sub]),
            "cost": _ms([r.get("cost", 0.0) for r in sub]),
            "pss": _ms([r.get("pss", 0.0) for r in sub]),
            "final_hv": _ms([r.get("final_hv", 0.0) for r in sub]),
        }
    return {"rows": rows, "summary": summary}


def experiment_trajectory(backend: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    print("E4 trajectory...", flush=True)
    r = run_method(
        "traj_peem_ppec", backend=backend, cfg=cfg, seed=42,
        preference="accuracy_first", cache_path=OUT / "cache_traj.json",
        log_episodes=False,
    )
    hist = r.get("history") or []
    marks = sorted(set([0, 2, 5, 10, cfg["gens"] - 1]) & set(range(len(hist))))
    curve = []
    for g in marks:
        h = hist[g]
        curve.append({
            "generation": g,
            "hypervolume": h.get("hypervolume"),
            "n_non_dominated": h.get("n_non_dominated"),
            "mutation_entropy": h.get("mutation_entropy"),
            "temperature": h.get("temperature"),
        })
    return {"curve": curve, "final_hv": r.get("final_hv"), "usage": r.get("cost_report", {}).get("llm_usage", {})}


def main() -> Dict[str, Any]:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", choices=list(SCALES), default="reduced")
    ap.add_argument("--backend", choices=["auto", "deepseek", "openai", "mock"], default="auto")
    args = ap.parse_args()
    cfg = SCALES[args.scale]
    backend = args.backend
    OUT.mkdir(parents=True, exist_ok=True)

    meta = {
        "scale": args.scale,
        "scale_config": cfg,
        "backend": backend,
        "paper_target": SCALES.get("paper"),
        "reduction_reason": "DeepSeek latency ~6s/call; wall-clock bound" if args.scale != "paper" else None,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    _write(OUT / "run_meta.json", meta)

    e1 = experiment_overall(backend, cfg)
    _write(OUT / "overall_results.json", e1)
    e2 = experiment_ablation(backend, cfg)
    _write(OUT / "ablation_results.json", e2)
    e3 = experiment_preference(backend, cfg)
    _write(OUT / "preference_results.json", e3)
    e4 = experiment_trajectory(backend, cfg)
    _write(OUT / "evolution_curve.json", e4)

    # Cost + cache aggregation
    all_reports = [r.get("cost_report") or {} for r in e1["rows"] + e2["rows"]]
    total_calls = 0
    total_tokens = 0
    total_cost = 0.0
    cache_hits = 0
    cache_misses = 0
    saved_cost = 0.0
    for rep in all_reports:
        u = rep.get("llm_usage") or {}
        total_calls += int(u.get("calls", 0))
        total_tokens += int(u.get("tokens", 0))
        total_cost += float(u.get("cost", 0.0))
        cs = rep.get("cache") or rep.get("cache_stats") or {}
        cache_hits += int(cs.get("hits", 0))
        cache_misses += int(cs.get("misses", 0))
        saved_cost += float(cs.get("saved_cost", 0.0))
    cost_report = {
        "scale": args.scale,
        "scale_config": cfg,
        "paper_target": SCALES.get("paper"),
        "llm_model": "deepseek-chat",
        "total_api_calls": total_calls,
        "total_tokens": total_tokens,
        "estimated_cost_usd": total_cost,
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "saved_calls": cache_hits,
        "estimated_cost_saving_usd": saved_cost,
        "budget_cap_usd": 20.0,
        "within_budget": total_cost <= 20.0,
    }
    _write(OUT / "cost_report.json", cost_report)

    summary = {
        "meta": meta,
        "overall": e1["summary"],
        "ablation": e2["summary"],
        "preference": e3["summary"],
        "evolution_curve": e4["curve"],
        "cost_report": cost_report,
    }
    _write(OUT / "final_summary.json", summary)
    print("Phase 4-R2 final experiment complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
