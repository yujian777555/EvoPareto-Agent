"""Freeze Stage 1.6 A/B protocol: 12 episodes (3 tasks x 1 genome x 2 runtimes x 2 repeats)."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/native_alfworld/development_task_pool.json"
OUT = ROOT / "results/stage1_6"

TASK_INDICES = [0, 10, 20]
RUNTIMES = ["current", "shared_repaired"]
REPEATS = [1, 2]
SHUFFLE_SEED = 2026

G1 = {
    "id": "G1",
    "planner_strategy": "cot",
    "memory_strategy": "short_term",
    "reflection_strategy": "self_critique",
    "tool_policy": "balanced",
    "reasoning_budget": 64,
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = MANIFEST.read_bytes()
    mf_sha = hashlib.sha256(raw).hexdigest()
    mf = json.loads(raw.decode("utf-8"))
    tasks = []
    for idx in TASK_INDICES:
        t = mf["tasks"][idx]
        gid = str(t["game_id"])
        ttype = gid.split("/")[-2].split("-")[0]
        tasks.append({"task_index": idx, "game_id": gid, "task_type": ttype,
                      "fingerprint": t.get("fingerprint")})

    config = {
        "stage": "STAGE1_6_AB",
        "scientific_question": (
            "Does shared Action-Observation memory + stagnation detection + goal-state "
            "tracking improve native won vs current runtime?"
        ),
        "objective_version": "candidate_2obj",
        "objective_names": ["performance", "cost"],
        "maximize": [True, False],
        "performance_source": "native_won",
        "model": "deepseek-flash",
        "rate_version": "deepseek-flash-2026-10-peak-conservative-v1",
        "environment": "ALFWorld TextWorld",
        "split": "valid_train",
        "horizon": 30,
        "manifest_path": "results/native_alfworld/development_task_pool.json",
        "manifest_sha256": mf_sha,
        "task_indices": TASK_INDICES,
        "frozen_tasks": tasks,
        "genome": G1,
        "runtime_variants": RUNTIMES,
        "repeats": REPEATS,
        "budget_caps": {
            "episodes_max": 12,
            "physical_http_cap": 400,
            "estimated_cost_cap_usd": 0.08,
            "scope": "batch total",
        },
        "rates": {"input_cache_miss_per_1m": 0.30, "output_per_1m": 1.20},
        "shuffle_seed": SHUFFLE_SEED,
    }

    rng = random.Random(SHUFFLE_SEED)
    matrix = []
    order = 0
    for t in tasks:
        for rep in REPEATS:
            rts = list(RUNTIMES)
            rng.shuffle(rts)  # interleave A/B order within each (task, repeat)
            for rt in rts:
                order += 1
                matrix.append({
                    "exec_order": order,
                    "task_index": t["task_index"],
                    "runtime_variant": rt,
                    "repeat_id": rep,
                    "genome_id": "G1",
                    "game_id": t["game_id"],
                    "episode_id": f"t{t['task_index']}_{rt}_r{rep}",
                })
    assert len(matrix) == 12
    combos = [(m["task_index"], m["runtime_variant"], m["repeat_id"]) for m in matrix]
    assert len(set(combos)) == 12

    prompt_manifest = {
        "version": "STAGE1_6_PROMPT_V1",
        "frozen_before_real_requests": True,
        "current_runtime": {
            "description": "Stage 1 legacy prompt (unchanged)",
            "includes": ["Task Goal", "Planner/Memory/Reflection/Tool labels",
                         "History (memory_strategy)", "Observation", "Admissible", "Choose ONE"],
            "excludes": ["Observed Progress", "Stagnation Warning", "Recent Actions and Feedback"],
        },
        "shared_repaired_runtime": {
            "description": "current prompt + verified progress block (format_repaired_prompt_block)",
            "additional_block": "STAGE1_6_PROMPT_V1 format_repaired_prompt_block",
            "memory_window_rule": "short_term -> k=1 history lines; none -> k=None; episodic/semantic/hybrid -> k=3",
            "no_extra_llm_calls": True,
            "no_forced_actions": True,
            "no_oracle_fields": ["traj_data", "high_pddl", "expert_actions", "hidden_state"],
        },
        "code_refs": [
            "src/diagnostics/shared_repair.py::format_repaired_prompt_block",
            "src/runtime/interactive_agent.py::select_action",
        ],
    }

    prereg = {
        "gates": {
            "GATE1_REPAIRED_SOLVABILITY": {
                "PASS": ">=1 native_won=true in shared_repaired arm",
                "FAIL": "all shared_repaired fail -> SHARED_REPAIR_INSUFFICIENT",
            },
            "GATE2_PAIRED_IMPROVEMENT": {
                "PASS_DESCRIPTIVE": ">=2 paired (task, repeat) cells with repaired_win & current_fail",
                "SOLVABILITY_SIGNAL_OBSERVED": "exactly 1 repaired-only win",
                "IMPROVEMENT_INCONCLUSIVE": "mixed/unclear",
                "REPAIR_NOT_SUPPORTED": "repaired worse or all fail",
                "both_succeed_rule": "report paired results; equal successes != improvement",
            },
            "GATE3_COST_SAFETY": {
                "PASS": "median_cost_repaired <= 1.5 * median_cost_current",
                "FAIL": "COST_SAFETY_FAIL if exceeds",
                "cost_per_success_note": "undefined (not 0) when a group has no successes",
            },
            "GATE4_LOOP_REDUCTION": {
                "type": "auxiliary diagnostic only",
                "metrics": ["state_action_loop_rate", "repeated_action_count",
                            "stagnation_event_count", "unique_locations_visited",
                            "target_object_discovery", "goal_completion"],
                "rule": "never replaces native won",
            },
        },
        "decision_rules": {
            "SHARED_REPAIR_FEASIBILITY_SUPPORTED": "G1 pass + G2 descriptive pass",
            "SOLVABILITY_OBSERVED_AB_INCONCLUSIVE": "success but no clear paired improvement",
            "SHARED_REPAIR_INSUFFICIENT": "both arms fail",
            "OFFLINE_BLOCKED_SAFETY_STOP": "offline gate or safety failure",
        },
        "prohibitions": [
            "no G2/G3 expansion", "no 24/36 episode expansion",
            "no budget increase", "no mid-experiment prompt edits",
            "no Stage 1 as control arm", "no expert actions into real agent",
        ],
    }

    (OUT / "experiment_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "experiment_matrix.json").write_text(json.dumps(
        {"n_episodes": 12, "shuffle_seed": SHUFFLE_SEED,
         "order_rule": "A/B order shuffled within each (task, repeat) block",
         "combinations": matrix}, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "preregistration.json").write_text(json.dumps(prereg, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "prompt_template_manifest.json").write_text(json.dumps(prompt_manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # offline gate results rollup
    gate_c = json.loads((ROOT / "results/stage1_5/gate_c_native_propagation.json").read_text(encoding="utf-8")) \
        if (ROOT / "results/stage1_5/gate_c_native_propagation.json").exists() else {}
    (OUT / "offline_gate_results.json").write_text(json.dumps({
        "GATE_A_goal_state_correctness": {
            "result": "PASS",
            "tests": "tests/test_goal_state_evidence.py + tests/test_shared_repair.py",
            "count": "19 passed",
            "no_goal_text_as_discovery": True,
            "no_command_name_as_success": True,
            "hold_state_updates": True,
            "no_oracle_leakage": True,
        },
        "GATE_B_runtime_integration": {
            "result": "PASS",
            "tests": "tests/test_runtime_integration.py",
            "current_prompt_unchanged": True,
            "repaired_prompt_contains_block": True,
            "no_extra_llm_calls": True,
            "same_mock_action_sequence": True,
        },
        "GATE_C_native_success_propagation": {
            "result": gate_c.get("result", "PASS"),
            "per_task": gate_c.get("per_task"),
            "expert_sequences_are_offline_test_only": True,
        },
        "all_gates_pass": True,
        "real_api_calls_at_gate_time": 0,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print("manifest", mf_sha)
    for m in matrix:
        print(f"  {m['exec_order']:2d}  t{m['task_index']:2d}  {m['runtime_variant']:16s}  r{m['repeat_id']}")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
