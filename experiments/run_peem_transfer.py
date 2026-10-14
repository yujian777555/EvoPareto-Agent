"""Phase5-Audit-3: PEEM memory transfer experiment.

Train PEEM experience on Benchmark A, evaluate mutation control on Benchmark B.

Baselines:
  1. Random mutation
  2. Fresh PEEM (no transfer)
  3. Transferred PEEM memory (loaded from A)

Core question: does PEEM learn reusable evolutionary knowledge?
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.evolution.adaptive_mutation import AdaptiveMutationController
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.pareto_experience import ParetoExperience
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "audit"
CONFIG = {"pop": 12, "gens": 6, "tasks": 8, "seeds": [11, 22, 33]}


def make_pipe(benchmark: str, seed: int) -> RealLLMPipeline:
    return RealLLMPipeline(
        RealLLMConfig(n_tasks=CONFIG["tasks"], backend="mock", seed=seed, benchmark=benchmark),
        cache=None,
    )


def train_experience(benchmark: str, seed: int) -> ParetoExperience:
    pipe = make_pipe(benchmark, seed)
    cfg = MemoryEvolutionConfig(
        pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
        use_adaptive=True, experience_mode="robust_peem",
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    loop.run(CONFIG["gens"])
    return loop.experience  # ParetoExperience


def run_on(
    benchmark: str,
    seed: int,
    *,
    mode: str,
    transferred: ParetoExperience | None = None,
) -> dict:
    pipe = make_pipe(benchmark, seed)
    if mode == "random":
        use_adaptive, exp_mode = False, "phase2"
    else:
        use_adaptive, exp_mode = True, "robust_peem"
    cfg = MemoryEvolutionConfig(
        pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
        use_adaptive=use_adaptive, experience_mode=exp_mode,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    if mode == "transfer_peem" and transferred is not None:
        # Inject transferred memory (copy) before run — controller reads scores.
        loop.experience = copy.deepcopy(transferred)
        loop.controller.experience = loop.experience
    loop.initialize()
    loop.run(CONFIG["gens"])
    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    return {
        "mode": mode, "benchmark": benchmark, "seed": seed,
        "success": sum(r[0] for r in rows) / len(rows) if rows else 0.0,
        "cost": sum(r[2] for r in rows) / len(rows) if rows else 0.0,
        "final_hv": loop.current_hypervolume(),
    }


def _ms(vals):
    n = len(vals)
    if not n:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / n
    return {"mean": m, "std": var ** 0.5}


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Train PEEM on ALFWorld...", flush=True)
    exps = {}
    for seed in CONFIG["seeds"]:
        exps[seed] = train_experience("alfworld", seed)

    print("Evaluate on WebShop: random / fresh PEEM / transferred PEEM...", flush=True)
    rows = []
    for seed in CONFIG["seeds"]:
        print(f"  seed={seed}", flush=True)
        rows.append(run_on("webshop", seed, mode="random"))
        rows.append(run_on("webshop", seed, mode="fresh_peem"))
        rows.append(run_on("webshop", seed, mode="transfer_peem", transferred=exps[seed]))

    summary = {}
    for mode in ("random", "fresh_peem", "transfer_peem"):
        sub = [r for r in rows if r["mode"] == mode]
        summary[mode] = {
            "success": _ms([r["success"] for r in sub]),
            "cost": _ms([r["cost"] for r in sub]),
            "final_hv": _ms([r["final_hv"] for r in sub]),
        }

    verdict = {
        "transfer_beats_random_success": (
            summary["transfer_peem"]["success"]["mean"] >= summary["random"]["success"]["mean"]
        ),
        "transfer_vs_fresh_hv": (
            summary["transfer_peem"]["final_hv"]["mean"] - summary["fresh_peem"]["final_hv"]["mean"]
        ),
        "interpretation": (
            "If transferred PEEM ≥ random and ≈ fresh PEEM, memory is reusable "
            "across benchmarks (algorithmic prior). If transfer < fresh, knowledge "
            "is partially benchmark-specific."
        ),
    }
    payload = {
        "phase": "Phase5-Audit-3 PEEM memory transfer",
        "train_benchmark": "alfworld",
        "test_benchmark": "webshop",
        "config": CONFIG,
        "summary": summary,
        "verdict": verdict,
        "runs": rows,
    }
    (OUT / "peem_transfer.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({"summary": summary, "verdict": verdict}, indent=2))
    return payload


if __name__ == "__main__":
    main()
