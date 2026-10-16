"""Run frozen FCEOL offline controlled experiment (no real API)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.fceol.offline_evaluator import run_full_experiment

OUT = ROOT / "results/stage2_0"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    res = run_full_experiment(seed=42)
    (OUT / "operator_policy_results.json").write_text(
        json.dumps(res["train"], indent=2), encoding="utf-8")
    (OUT / "heldout_results.json").write_text(
        json.dumps(res["heldout"], indent=2), encoding="utf-8")
    (OUT / "intervention_results.json").write_text(
        json.dumps({
            "train": res["train"],
            "n_train": res["n_train"],
            "n_dev": res["n_dev"],
            "n_test": res["n_test"],
        }, indent=2), encoding="utf-8")
    # shuffled-label control summary
    (OUT / "shuffled_label_results.json").write_text(
        json.dumps({
            "train_shuffled": res["train"].get("shuffled"),
            "heldout_shuffled": res["heldout"].get("shuffled"),
            "train_fceol": res["train"].get("fceol"),
            "heldout_fceol": res["heldout"].get("fceol"),
        }, indent=2), encoding="utf-8")

    summary = {
        "train_mean_delta": {k: v["mean_delta"] for k, v in res["train"].items()},
        "heldout_mean_delta": {k: v["mean_delta"] for k, v in res["heldout"].items()},
        "train_success_rate": {k: v["success_rate"] for k, v in res["train"].items()},
        "heldout_success_rate": {k: v["success_rate"] for k, v in res["heldout"].items()},
        "fceol_vs_global_train_delta": res["train"]["fceol"]["mean_delta"] - res["train"]["global_aos"]["mean_delta"],
        "fceol_vs_global_heldout_delta": res["heldout"]["fceol"]["mean_delta"] - res["heldout"]["global_aos"]["mean_delta"],
        "fceol_vs_shuffled_heldout_delta": res["heldout"]["fceol"]["mean_delta"] - res["heldout"]["shuffled"]["mean_delta"],
    }
    (OUT / "test_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
