"""Dump objective diagnostics + attempt native positive control (train split)."""

from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/")
os.environ.setdefault("ALFWORLD_DATA", "/data")

from src.evaluation.objective_diagnostics import (
    autonomy_from_behavior,
    cost_resolution,
    efficiency_conditional_candidate,
    efficiency_counterexamples,
    full_audit_table,
    plan_a_vs_plan_b,
    robustness_redundancy,
)


def positive_control() -> dict:
    """Try expert_planner path to show env can reach won=True (train only)."""
    try:
        from alfworld.agents.environment.alfred_tw_env import AlfredTWEnv

        data = os.environ.get("ALFWORLD_DATA", "/data")
        cfg = {
            "general": {"training_method": "dagger"},
            "env": {
                "goal_desc_human_anns_prob": 0.0,
                "task_types": [0, 1, 2, 3, 4, 5, 6],
                "domain_randomization": False,
                "expert_type": "planner",
            },
            "dataset": {
                "data_path": f"{data}/json_2.1.1/valid_train",
                "eval_id_data_path": f"{data}/json_2.1.1/valid_seen",
                "eval_ood_data_path": f"{data}/json_2.1.1/valid_unseen",
                "num_train_games": 1,
                "num_eval_games": 1,
            },
            "dagger": {"training": {"max_nb_steps_per_episode": 40}},
            "rl": {"training": {"max_nb_steps_per_episode": 40}},
        }
        wrap = AlfredTWEnv(config=cfg, train_eval="train")
        if wrap.num_games == 0:
            return {"ok": False, "reason": "no train games"}
        # Use expert planner on a single game via env.load / expert plan if available
        game = wrap.game_files[0]
        return {
            "ok": True,
            "mode": "expert_plan_available_check",
            "game_id": game,
            "expert_type": "planner",
            "note": "Positive control requires dagger expert_plan extras; if missing, report incomplete.",
            "won": None,
        }
    except Exception as e:
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def main():
    out = "/results/native_alfworld/objective_diagnostics"
    os.makedirs(out, exist_ok=True)
    ex = efficiency_counterexamples(20)
    audit = full_audit_table()
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "efficiency_counterexamples": ex,
        "efficiency_conditional_candidate": {
            "fail_quick": efficiency_conditional_candidate(False, 1, 20, 20),
            "success_long": efficiency_conditional_candidate(True, 12, 500, 20),
        },
        "robustness_redundancy": robustness_redundancy(0.0, 0.4),
        "autonomy_behavior_candidate": {
            "clean": autonomy_from_behavior(10, 0, 0),
            "fallback_heavy": autonomy_from_behavior(10, 5, 2),
        },
        "cost_resolution_micro": cost_resolution([0.001, 0.003]),
        "audit_table": audit,
        "plan_a_vs_plan_b": plan_a_vs_plan_b(),
        "positive_control": positive_control(),
    }
    with open(f"{out}/objective_validity.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", out)
    print(json.dumps({"ex": ex, "audit_invalid": [r["objective"] for r in audit if not r["valid"]]}))


if __name__ == "__main__":
    main()
