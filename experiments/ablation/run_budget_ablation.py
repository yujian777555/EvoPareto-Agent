"""Experiment 5: Budget-controlled comparison (fixed evaluation budget).

All methods receive the same number of genome evaluations
(pop * (gens + 1)). Tracks HV vs evaluation budget curves.

Answers: "are gains just from more evaluations?"
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
    finalize_igd,
    ms,
    run_variant,
    write_json,
)

KEYS = ("hypervolume", "igd", "success", "cost", "evaluations")


def main() -> dict:
    cfg = ABLATION_CONFIG
    pop, gens = cfg["pop"], cfg["gens"]
    budget = pop * (gens + 1)  # identical for every method
    variants = {
        "Random": dict(use_adaptive=False, experience_mode="phase2"),
        "Success_adaptive": dict(use_adaptive=True, experience_mode="phase2"),
        "NSGA3_PEEM": dict(use_adaptive=True, experience_mode="robust_peem"),
        "PEEM_PPEC": dict(use_adaptive=True, experience_mode="robust_peem", preference="balanced"),
    }
    runs = []
    for seed in cfg["seeds"]:
        for name, kw in variants.items():
            print(f"  budget {name} seed={seed}", flush=True)
            runs.append(run_variant(
                name, seed=seed,
                pop=pop, gens=gens, tasks=cfg["tasks"],
                track_curve=True, **kw,
            ))
    all_rows = [row for r in runs for row in r.population_rows]
    finalize_igd(runs, all_rows)

    # HV vs evaluation-budget curve (mean over seeds).
    curves = {}
    for name in variants:
        series = []
        for r in runs:
            if r.name != name:
                continue
            pts = []
            for h in r.history:
                g = int(h.get("generation", 0))
                pts.append({"evals": pop * (g + 1), "hypervolume": h.get("hypervolume", 0.0)})
            series.append(pts)
        if not series:
            curves[name] = []
            continue
        n = max(len(s) for s in series)
        mean_curve = []
        for i in range(n):
            vals = [s[i]["hypervolume"] for s in series if i < len(s) and s[i]["hypervolume"] is not None]
            evals = series[0][i]["evals"] if i < len(series[0]) else None
            mean_curve.append({"evals": evals, "hypervolume_mean": sum(vals) / len(vals) if vals else 0.0})
        curves[name] = mean_curve

    summary = {}
    for name in variants:
        sub = [r for r in runs if r.name == name]
        summary[name] = {
            k: ms([r.metrics.get(k, 0.0) for r in sub]) for k in KEYS
        }
        # Ensure every method reports the same budget.
        summary[name]["fixed_budget_evals"] = budget

    payload = {
        "experiment": "E5_budget_controlled",
        "config": cfg,
        "fixed_evaluation_budget": budget,
        "table": [
            {
                "Method": k,
                "Evaluations": budget,
                "HV": summary[k]["hypervolume"],
                "Success": summary[k]["success"],
                "Cost": summary[k]["cost"],
            }
            for k in variants
        ],
        "hv_vs_evals": curves,
        "summary": summary,
        "runs": [r.to_dict() for r in runs],
    }
    write_json(RESULTS / "budget.json", payload)
    print("E5 budget-controlled complete. budget=", budget)
    for row in payload["table"]:
        print(row)
    return payload


if __name__ == "__main__":
    main()
