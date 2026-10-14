"""Run all Phase 5-Pre ablations and write combined statistics."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from experiments.ablation.harness import RESULTS, ms, write_json
from experiments.ablation import (
    run_budget_ablation,
    run_framework_ablation,
    run_peem_ablation,
    run_preference_ablation,
)


def main() -> dict:
    RESULTS.mkdir(parents=True, exist_ok=True)
    print("=== E1 Framework ===", flush=True)
    e1 = run_framework_ablation.main()
    print("=== E2/E3 PEEM ===", flush=True)
    e2 = run_peem_ablation.main()
    print("=== E4 Preference ===", flush=True)
    e4 = run_preference_ablation.main()
    print("=== E5 Budget ===", flush=True)
    e5 = run_budget_ablation.main()

    # Combined statistical rollup (mean ± std already inside each summary).
    stats = {
        "phase": "Phase 5-Pre comprehensive ablation",
        "seeds": e1["config"]["seeds"],
        "n_seeds": len(e1["config"]["seeds"]),
        "framework": e1["table"],
        "peem_components": e2["component_table"],
        "mutation_strategies": e2["mutation_strategies"]["table"],
        "preference": e4["table"],
        "budget": e5["table"],
        "fixed_budget_evals": e5.get("fixed_evaluation_budget"),
    }
    write_json(RESULTS / "all_ablations_summary.json", stats)
    print("All ablations complete ->", RESULTS)
    print(json.dumps(stats, indent=2, ensure_ascii=False)[:2500])
    return stats


if __name__ == "__main__":
    main()
