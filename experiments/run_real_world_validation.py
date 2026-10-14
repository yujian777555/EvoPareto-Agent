"""Phase 5-R1: Real-world tool-use agent validation.

E1 Overall performance
E2 Evolution effect (gen 0/1/3/5)
E3 Preference validation
E4 Agent transfer (train 70% → test 30%)

Usage:
    python experiments/run_real_world_validation.py
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

from src.agent.genome import AgentGenome
from src.benchmark.real_world_agent import RealWorldAgentBenchmark
from src.evaluation.metrics import preference_satisfaction_score
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.preference import encode_preference
from src.runtime.agent_builder import AgentBuilder
from src.runtime.cache import EvaluationCache
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "real_world"

# Paper target 8/5/50/3; shipped uses 8/5/50/3 on mock (fast).
CONFIG = {"pop": 8, "gens": 5, "tasks": 50, "seeds": [11, 22, 33], "budget_evals": 8 * 6}


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


def make_pipeline(seed: int, *, split: str = "all", n_tasks: int | None = None) -> RealLLMPipeline:
    cache = EvaluationCache(OUT / "cache_real_world.json")
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=n_tasks or CONFIG["tasks"], backend="mock", seed=seed),
        cache=cache,
    )
    # Swap in real-world adapter (same contract).
    pipe.adapter = RealWorldAgentBenchmark(
        n_tasks=n_tasks or CONFIG["tasks"],
        seed=seed,
        backend=pipe.backend,
        cache=cache,
        split=split,
    )
    if hasattr(pipe.adapter, "max_workers"):
        pipe.adapter.max_workers = 4
    return pipe


def run_evolved(
    name: str,
    *,
    seed: int,
    preference=None,
    use_adaptive: bool = True,
    experience_mode: str = "robust_peem",
    split: str = "all",
    track_curve: bool = False,
) -> Dict[str, Any]:
    t0 = time.time()
    pipe = make_pipeline(seed, split=split)
    cfg = MemoryEvolutionConfig(
        pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
        use_adaptive=use_adaptive, experience_mode=experience_mode,
        preference=preference,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    curve = [dict(h) for h in loop.history]
    for _ in range(CONFIG["gens"]):
        loop.next_generation()
        if track_curve:
            curve.append(dict(loop.history[-1]))
    if not track_curve:
        curve = list(loop.history)
    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    pref = encode_preference(preference) if preference is not None else encode_preference("balanced")
    # Tool-call stats from a re-eval of the front.
    agent0 = pipe.builder.build(loop.pareto_front()[0].genome, agent_id=0) if loop.pareto_front() else None
    tool_calls = 0
    tool_ok = 0.0
    if agent0 is not None:
        ep = pipe.adapter.run(agent0)
        tool_calls = sum(len(r.metadata.get("tool_calls") or []) for r in ep.results)
        tool_ok = sum(1 for r in ep.results if r.metadata.get("tool_success")) / max(1, ep.n_tasks)
    return {
        "method": name, "seed": seed, "split": split,
        "success": sum(r[0] for r in rows) / len(rows) if rows else 0.0,
        "cost": sum(r[2] for r in rows) / len(rows) if rows else 0.0,
        "efficiency": sum(r[1] for r in rows) / len(rows) if rows else 0.0,
        "latency_proxy": 1.0 - sum(r[1] for r in rows) / len(rows) if rows else 0.0,
        "pss": preference_satisfaction_score(rows, pref) if rows else 0.0,
        "tool_calls": tool_calls,
        "tool_success": tool_ok,
        "final_hv": loop.current_hypervolume(),
        "curve": curve,
        "cost_report": pipe.cost_report(),
        "wall_time": time.time() - t0,
    }


def evaluate_fixed(genome: AgentGenome, *, seed: int, name: str, split: str = "all") -> Dict[str, Any]:
    pipe = make_pipeline(seed, split=split)
    agent = pipe.builder.build(genome, agent_id=0)
    ep, recs = pipe.adapter.run_recorded(agent)
    vec = pipe.objectives.from_episode(ep)
    return {
        "method": name, "seed": seed, "split": split,
        "success": vec[0], "cost": vec[2], "efficiency": vec[1],
        "latency_proxy": 1.0 - vec[1],
        "pss": preference_satisfaction_score([vec], encode_preference("balanced")),
        "tool_calls": sum(len(r.metadata.get("tool_calls") or []) for r in ep.results),
        "tool_success": sum(1 for r in ep.results if r.metadata.get("tool_success")) / max(1, ep.n_tasks),
        "cost_report": pipe.cost_report(),
    }


METHODS = {
    "B2_nsga3": dict(use_adaptive=False, experience_mode="phase2"),
    "B3_nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem"),
    "B4_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
}


def experiment_overall() -> Dict[str, Any]:
    print("E1 overall...", flush=True)
    rows = []
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    for seed in CONFIG["seeds"]:
        print(f"  B1_react seed={seed}", flush=True)
        rows.append(evaluate_fixed(react, seed=seed, name="B1_react"))
        for name, kw in METHODS.items():
            print(f"  {name} seed={seed}", flush=True)
            rows.append(run_evolved(name, seed=seed, **kw))
    table = []
    for name in ["B1_react", "B2_nsga3", "B3_nsga3_peem", "B4_peem_ppec"]:
        sub = [r for r in rows if r["method"] == name]
        table.append({
            "Method": name,
            "Success": _ms([r["success"] for r in sub]),
            "Cost": _ms([r["cost"] for r in sub]),
            "Latency": _ms([r.get("latency_proxy", 0.0) for r in sub]),
            "ToolCalls": _ms([float(r.get("tool_calls", 0)) for r in sub]),
            "ToolSuccess": _ms([r.get("tool_success", 0.0) for r in sub]),
        })
    return {"table": table, "runs": [{k: v for k, v in r.items() if k != "cost_report"} for r in rows]}


def experiment_trajectory() -> Dict[str, Any]:
    print("E2 trajectory...", flush=True)
    out = run_evolved("traj", seed=42, preference="accuracy_first", track_curve=True)
    marks = [0, 1, 3, 5]
    curve = []
    for g in marks:
        if g < len(out["curve"]):
            h = out["curve"][g]
            curve.append({
                "generation": g,
                "hypervolume": h.get("hypervolume"),
                "success_proxy": h.get("fitness_sum"),
                "n_non_dominated": h.get("n_non_dominated"),
            })
    return {"curve": curve, "final_hv": out["final_hv"]}


def experiment_preference() -> Dict[str, Any]:
    print("E3 preference...", flush=True)
    rows = []
    for seed in CONFIG["seeds"]:
        for pref in ("accuracy_first", "cost_first", "balanced"):
            print(f"  {pref} seed={seed}", flush=True)
            r = run_evolved(f"pref_{pref}", seed=seed, preference=pref)
            rows.append({"preference": pref, **{k: r[k] for k in
                        ("seed", "success", "cost", "pss", "tool_success")}})
    table = []
    for pref in ("accuracy_first", "cost_first", "balanced"):
        sub = [r for r in rows if r["preference"] == pref]
        table.append({
            "Preference": pref,
            "Success": _ms([r["success"] for r in sub]),
            "Cost": _ms([r["cost"] for r in sub]),
            "PSS": _ms([r["pss"] for r in sub]),
        })
    return {"table": table, "runs": rows}


def experiment_transfer() -> Dict[str, Any]:
    print("E4 transfer...", flush=True)
    rows = []
    react = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    for seed in CONFIG["seeds"]:
        # Evolve on train split
        train = run_evolved("B4_peem_ppec", seed=seed, preference="balanced", split="train")
        # Evaluate evolved front-best vs ReAct on test split
        pipe_train = make_pipeline(seed, split="train")
        cfg = MemoryEvolutionConfig(
            pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
            use_adaptive=True, experience_mode="robust_peem", preference="balanced",
        )
        loop = MemoryEvolutionLoop(evaluator=pipe_train.as_evaluate_fn(), config=cfg)
        loop.initialize()
        loop.run(CONFIG["gens"])
        best = max(loop.individuals, key=lambda i: i.fitness_vector[0] if i.fitness_vector else 0)

        pipe_test = make_pipeline(seed, split="test")
        agent = pipe_test.builder.build(best.genome, agent_id=0)
        ep = pipe_test.adapter.run(agent)
        vec = pipe_test.objectives.from_episode(ep)

        agent_r = pipe_test.builder.build(react, agent_id=1)
        ep_r = pipe_test.adapter.run(agent_r)
        vec_r = pipe_test.objectives.from_episode(ep_r)

        rows.append({
            "seed": seed,
            "evolved_test_success": vec[0],
            "evolved_test_cost": vec[2],
            "react_test_success": vec_r[0],
            "react_test_cost": vec_r[2],
            "train_success": train["success"],
        })
    return {
        "table": {
            "evolved_test_success": _ms([r["evolved_test_success"] for r in rows]),
            "react_test_success": _ms([r["react_test_success"] for r in rows]),
            "evolved_test_cost": _ms([r["evolved_test_cost"] for r in rows]),
            "react_test_cost": _ms([r["react_test_cost"] for r in rows]),
        },
        "runs": rows,
    }


def main() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    e1 = experiment_overall()
    _write(OUT / "overall.json", e1)
    e2 = experiment_trajectory()
    _write(OUT / "trajectory.json", e2)
    e3 = experiment_preference()
    _write(OUT / "preference.json", e3)
    e4 = experiment_transfer()
    _write(OUT / "transfer.json", e4)

    # Cache report (persist last cache + aggregate run-level stats)
    pipe = make_pipeline(CONFIG["seeds"][0])
    if pipe.cache.path:
        pipe.cache.save_json(pipe.cache.path)
    hits = sum(int((r.get("cost_report") or {}).get("cache_stats", {}).get("hits", 0))
               for r in e1.get("runs", []) if isinstance(r, dict))
    # E1 runs strip cost_report; use live cache stats instead.
    cost_report = {
        "config": CONFIG,
        "cache": pipe.cache.stats(),
        "note": "cache file results/real_world/cache_real_world.json; per-run hits counted at evaluate time",
    }
    _write(OUT / "cost_report.json", cost_report)
    summary = {"config": CONFIG, "overall": e1["table"], "trajectory": e2,
               "preference": e3["table"], "transfer": e4["table"], "cost_report": cost_report}
    _write(OUT / "summary.json", summary)
    print("Phase 5-R1 real-world validation complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False)[:2500])
    return summary


if __name__ == "__main__":
    main()
