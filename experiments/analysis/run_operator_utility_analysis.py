"""Phase5-R2: export operator utility time-series for ALFWorld & WebShop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evolution.memory_evolution import MemoryEvolutionConfig
from src.evolution.operator_logging import (
    OPERATORS,
    LoggingLoop,
    aggregate_seed_timeseries,
)
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "analysis"
CONFIG = {"pop": 16, "gens": 10, "tasks": 8, "seeds": [11, 22, 33]}


def run_one(benchmark: str, seed: int) -> dict:
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=CONFIG["tasks"], backend="mock", seed=seed, benchmark=benchmark),
        cache=None,
    )
    cfg = MemoryEvolutionConfig(
        pop_size=CONFIG["pop"], n_offspring=CONFIG["pop"], seed=seed,
        use_adaptive=True, experience_mode="robust_peem",
    )
    loop = LoggingLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.logger.benchmark = benchmark
    loop.logger.seed = seed
    loop.initialize()
    loop.run(CONFIG["gens"])
    return loop.logger.to_dict()


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    all_data = {}
    for bench in ("alfworld", "webshop"):
        print(f"=== {bench} ===", flush=True)
        seed_runs = []
        for seed in CONFIG["seeds"]:
            print(f"  seed={seed}", flush=True)
            d = run_one(bench, seed)
            seed_runs.append(d)
            (OUT / f"operator_utility_{bench}_seed{seed}.json").write_text(
                json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        agg = aggregate_seed_timeseries(seed_runs)
        payload = {
            "benchmark": bench,
            "seeds": CONFIG["seeds"],
            "config": CONFIG,
            "operators": list(OPERATORS),
            "aggregated": agg,
            "per_seed": seed_runs,
        }
        path = OUT / f"operator_utility_{bench}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        all_data[bench] = payload
        # quick print
        for op in OPERATORS:
            last_u = agg["operators"][op]["utility_mean"][-1]
            last_p = agg["operators"][op]["probability_mean"][-1]
            print(f"  {op:12s} final_utility={last_u:.4f} final_prob={last_p:.4f}")

    # Combined timeseries file
    combined = {
        "config": CONFIG,
        "benchmarks": list(all_data.keys()),
        "data": {b: all_data[b]["aggregated"] for b in all_data},
    }
    (OUT / "operator_utility_timeseries.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("Wrote", OUT / "operator_utility_timeseries.json")
    return all_data


if __name__ == "__main__":
    main()
