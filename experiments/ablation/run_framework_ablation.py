"""Experiment 1: Framework ablation A1/A2/A3.

A1: NSGA-III
A2: NSGA-III + PEEM
A3: NSGA-III + PEEM + PPEC

Same pop / gens / tasks / seeds / LLM budget. Mock backend for reproducibility.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.ablation.harness import (
    ABLATION_CONFIG,
    RESULTS,
    aggregate,
    finalize_igd,
    run_variant,
    write_json,
)

KEYS = ("hypervolume", "igd", "success", "cost", "pss", "efficiency", "mutation_entropy")


def main() -> dict:
    cfg = ABLATION_CONFIG
    variants = {
        "A1_nsga3": dict(use_adaptive=False, experience_mode="phase2", preference=None),
        "A2_nsga3_peem": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "A3_nsga3_peem_ppec": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
    }
    runs = []
    for seed in cfg["seeds"]:
        for name, kw in variants.items():
            print(f"  framework {name} seed={seed}", flush=True)
            runs.append(run_variant(
                name, seed=seed,
                pop=cfg["pop"], gens=cfg["gens"], tasks=cfg["tasks"], **kw,
            ))
    all_rows = [row for r in runs for row in r.population_rows]
    finalize_igd(runs, all_rows)
    summary = aggregate(runs, KEYS)
    table = []
    for name in variants:
        s = summary[name]
        table.append({
            "Method": name,
            "HV": s["hypervolume"],
            "IGD": s["igd"],
            "Success": s["success"],
            "Cost": s["cost"],
            "PSS": s["pss"],
        })
    payload = {
        "experiment": "E1_framework_ablation",
        "config": cfg,
        "table": table,
        "summary": summary,
        "runs": [r.to_dict() for r in runs],
    }
    write_json(RESULTS / "framework.json", payload)
    print("E1 framework ablation complete.")
    for row in table:
        print(row)
    return payload


if __name__ == "__main__":
    main()
