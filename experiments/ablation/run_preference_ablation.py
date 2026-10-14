"""Experiment 4: Preference ablation (PPEC).

Fixed PEEM on. Compare PEEM vs PEEM+PPEC under three preferences.
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

KEYS = ("hypervolume", "igd", "success", "cost", "pss")


def main() -> dict:
    cfg = ABLATION_CONFIG
    prefs = ["accuracy_first", "cost_first", "balanced"]
    methods = {
        "PEEM": dict(use_adaptive=True, experience_mode="robust_peem", preference=None),
        "PEEM_PPEC": dict(use_adaptive=True, experience_mode="robust_peem"),
    }
    runs = []
    for seed in cfg["seeds"]:
        for pref in prefs:
            for method, kw in methods.items():
                print(f"  pref={pref} {method} seed={seed}", flush=True)
                call = dict(kw)
                if method == "PEEM_PPEC":
                    call["preference"] = pref
                runs.append(run_variant(
                    f"{method}|{pref}", seed=seed,
                    pop=cfg["pop"], gens=cfg["gens"], tasks=cfg["tasks"],
                    **call,
                ))
    all_rows = [row for r in runs for row in r.population_rows]
    finalize_igd(runs, all_rows)
    summary = aggregate(runs, KEYS)
    table = []
    for pref in prefs:
        for method in methods:
            key = f"{method}|{pref}"
            s = summary[key]
            table.append({
                "Preference": pref,
                "Method": method,
                "PSS": s["pss"],
                "HV": s["hypervolume"],
                "Cost": s["cost"],
            })
    payload = {
        "experiment": "E4_preference_ablation",
        "config": cfg,
        "table": table,
        "summary": summary,
        "runs": [r.to_dict() for r in runs],
    }
    write_json(RESULTS / "preference.json", payload)
    print("E4 preference ablation complete.")
    for row in table:
        print(row)
    return payload


if __name__ == "__main__":
    main()
