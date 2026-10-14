"""Experiment 2+3: PEEM component ablation and mutation-strategy comparison.

PEEM-w/o-Pareto     : pareto credit weight = 0
PEEM-w/o-Diversity  : diversity weight = 0
PEEM-w/o-Delay      : use_delayed_credit = False
PEEM-w/o-Temperature: use_softmax = False
Full PEEM           : all components

E3 compares Random / Success-rate / PEEM mutation strategies.
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
from src.evolution.credit_assignment import CreditWeights

KEYS = ("hypervolume", "igd", "success", "cost", "pss", "mutation_entropy")


def main() -> dict:
    cfg = ABLATION_CONFIG
    # Component variants (config-only ablations; algorithm code unchanged).
    components = {
        "PEEM_full": dict(use_adaptive=True, experience_mode="robust_peem",
                          credit_weights=CreditWeights(0.35, 0.30, 0.20, 0.15)),
        "PEEM_w_o_Pareto": dict(use_adaptive=True, experience_mode="robust_peem",
                                credit_weights=CreditWeights(0.55, 0.0, 0.25, 0.20)),
        "PEEM_w_o_Diversity": dict(use_adaptive=True, experience_mode="robust_peem",
                                   credit_weights=CreditWeights(0.50, 0.35, 0.0, 0.15)),
        "PEEM_w_o_Delay": dict(use_adaptive=True, experience_mode="robust_peem",
                               use_delayed=False),
        "PEEM_w_o_Temperature": dict(use_adaptive=True, experience_mode="robust_peem",
                                     use_softmax=False),
    }
    runs = []
    for seed in cfg["seeds"]:
        for name, kw in components.items():
            print(f"  peem-component {name} seed={seed}", flush=True)
            runs.append(run_variant(
                name, seed=seed,
                pop=cfg["pop"], gens=cfg["gens"], tasks=cfg["tasks"], **kw,
            ))
    all_rows = [row for r in runs for row in r.population_rows]
    finalize_igd(runs, all_rows)
    comp_summary = aggregate(runs, KEYS)
    # Convergence proxy: HV at final gen (from history last entry).
    conv = {}
    for name in components:
        vals = []
        for r in runs:
            if r.name == name and r.history:
                vals.append(float(r.history[-1].get("hypervolume", 0.0)))
        conv[name] = {"final_hv_curve": {"mean": sum(vals) / len(vals) if vals else 0.0,
                                         "std": 0.0}}

    # E3 mutation strategy comparison (same budget).
    strategy = {
        "Random_mutation": dict(use_adaptive=False, experience_mode="phase2"),
        "Success_rate_adaptive": dict(use_adaptive=True, experience_mode="phase2"),
        "PEEM": dict(use_adaptive=True, experience_mode="robust_peem"),
    }
    strat_runs = []
    for seed in cfg["seeds"]:
        for name, kw in strategy.items():
            print(f"  mutation-strategy {name} seed={seed}", flush=True)
            strat_runs.append(run_variant(
                name, seed=seed,
                pop=cfg["pop"], gens=cfg["gens"], tasks=cfg["tasks"], **kw,
            ))
    all_strat = [row for r in strat_runs for row in r.population_rows]
    finalize_igd(strat_runs, all_strat)
    strat_summary = aggregate(strat_runs, KEYS)

    payload = {
        "experiment": "E2_peem_component_ablation",
        "config": cfg,
        "component_table": [
            {
                "Variant": k,
                "HV": comp_summary[k]["hypervolume"],
                "IGD": comp_summary[k]["igd"],
                "Convergence": conv.get(k, {}),
            }
            for k in components
        ],
        "summary": comp_summary,
        "mutation_strategies": {
            "experiment": "E3_mutation_strategy_comparison",
            "table": [
                {
                    "Strategy": k,
                    "HV": strat_summary[k]["hypervolume"],
                    "EvalEfficiency": strat_summary[k]["success"],
                    "MutationEntropy": strat_summary[k]["mutation_entropy"],
                }
                for k in strategy
            ],
            "summary": strat_summary,
        },
        "runs": [r.to_dict() for r in runs + strat_runs],
    }
    write_json(RESULTS / "peem_components.json", payload)
    print("E2/E3 PEEM ablation complete.")
    for row in payload["component_table"]:
        print(row)
    for row in payload["mutation_strategies"]["table"]:
        print(row)
    return payload


if __name__ == "__main__":
    main()
