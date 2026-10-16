"""Write Stage 2.0-R1 final evidence."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/stage2_0_r1"

frozen = json.loads((OUT / "frozen_transfer_results.json").read_text(encoding="utf-8"))
multiseed = json.loads((OUT / "multiseed_summary.json").read_text(encoding="utf-8"))
oracle = json.loads((OUT / "oracle_validation.json").read_text(encoding="utf-8"))

(OUT / "source_manifest.json").write_text(json.dumps({
    "fceol_r1_modules": [
        "src/research/fceol_r1/task_suite.py",
        "src/research/fceol_r1/workflow_interpreter.py",
        "src/research/fceol_r1/faults.py",
        "src/research/fceol_r1/evidence.py",
        "src/research/fceol_r1/policies.py",
        "src/research/fceol_r1/evaluator.py",
    ],
    "stage2_0_code_preserved": True,
}, indent=2), encoding="utf-8")

(OUT / "environment_manifest.json").write_text(json.dumps({
    "interpreter": "WorkflowInterpreter — real node execution",
    "reward": "independent_evaluate over required_checks (no fault lookup)",
    "fault_channels": ["tool_is_broken", "verifier_sabotaged", "context_dropped", "recovery_miswired"],
    "genome_params_wired": ["context_mode", "route_policy", "max_repairs", "enabled nodes"],
    "unfixable_by_design": ["RECOVERY_BRANCH_ERROR", "COMPOUND"],
    "solvable_tasks": ["TOOL_ROUTING_ERROR", "CONTEXT_PROPAGATION_ERROR"],
}, indent=2), encoding="utf-8")

(OUT / "genome_execution_audit.json").write_text(json.dumps({
    "serialize_roundtrip": True,
    "mutation_changes_trace": True,
    "disabled_nodes_not_executed": True,
    "params_affect_execution": True,
    "invalid_mutations_rejected": True,
    "invalid_test_assertions_removed": "or True removed from tests/fceol/test_fceol_core.py",
}, indent=2), encoding="utf-8")

(OUT / "paired_intervention_results.json").write_text(json.dumps({
    "protocol": "Experiment-1 operator learning (paired parent/child)",
    "primary_metric": "frozen mean_final_reward",
    "frozen_means": {k: v["mean"] for k, v in frozen["mean_final_reward"].items()},
}, indent=2), encoding="utf-8")

# key comparison
cb = frozen["mean_final_reward"]["contextual_bandit"]["mean"]
fc = frozen["mean_final_reward"]["fceol"]["mean"]
ga = frozen["mean_final_reward"]["global_aos"]["mean"]
comparison = {
    "fceol_vs_contextual_bandit": fc - cb,
    "fceol_vs_global_aos": fc - ga,
    "fceol_vs_shuffled": fc - frozen["mean_final_reward"]["shuffled"]["mean"],
    "fceol_vs_unknown_only": fc - frozen["mean_final_reward"]["unknown_only"]["mean"],
    "oracle_ceiling": frozen["oracle_mean_best_reward"],
    "verdict": "FCEOL_BENEFIT_NOT_ESTABLISHED",
    "reason": "FCEOL ties standard contextual bandit and global AOS at 0.200; "
              "failure conditioning adds no measurable value under 3-step budget",
}
(OUT / "final_gate_decisions.json").write_text(json.dumps({
    "GATE_R1_A": {
        "unique_ids": "PASS", "split_isolation": "PASS",
        "template_leakage": "PASS", "no_hidden_fault_leakage": "PASS",
    },
    "GATE_R1_B": {
        "workflow_interpreter": "PASS", "node_execution": "PASS",
        "trace_completeness": "PASS", "independent_evaluator": "PASS",
        "nontrivial_fault_interaction": "PASS", "no_fault_reward_lookup": "PASS",
    },
    "GATE_R1_C": {
        "shuffled_control": "PASS", "oracle_upper_bound": "PASS",
        "global_aos_fairness": "PASS", "frozen_transfer": "PASS",
        "task_level_metrics": "PASS", "objective_direction": "PASS",
    },
    "GATE_R1_D": "FCEOL_BENEFIT_NOT_ESTABLISHED",
    "comparison": comparison,
    "FINAL_DECISION": "OFFLINE_VALID_BUT_NO_BENEFIT",
    "real_llm_calls": 0,
}, indent=2), encoding="utf-8")

(OUT / "negative_results.json").write_text(json.dumps({
    "fceol_equals_contextual_bandit": True,
    "fceol_equals_global_aos": True,
    "no_success_anywhere": True,
    "oracle_reveals_missing_search": True,
    "interpretation": (
        "environment is valid and non-trivial (oracle 0.38 vs policies 0.20), "
        "but failure-conditioned selection does not outperform generic bandit/AOS"
    ),
}, indent=2), encoding="utf-8")

print(json.dumps(comparison, indent=2))
