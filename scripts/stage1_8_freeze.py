"""Stage 1.8 freeze: 6-episode A/B protocol + prompt manifest."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/native_alfworld/development_task_pool.json"
OUT = ROOT / "results/stage1_8"

TASK_INDICES = [0, 10, 20]
RUNTIMES = ["current", "grounded_planner_v1"]
G1 = {"id": "G1", "planner_strategy": "cot", "memory_strategy": "short_term",
      "reflection_strategy": "self_critique", "tool_policy": "balanced", "reasoning_budget": 64}
SHUFFLE_SEED = 2026


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = MANIFEST.read_bytes()
    mf_sha = hashlib.sha256(raw).hexdigest()
    assert mf_sha == "27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7", mf_sha
    mf = json.loads(raw.decode("utf-8"))
    tasks = []
    for idx in TASK_INDICES:
        t = mf["tasks"][idx]
        gid = str(t["game_id"])
        tasks.append({"task_index": idx, "game_id": gid,
                      "task_type": gid.split("/")[-2].split("-")[0],
                      "fingerprint": t.get("fingerprint")})

    config = {
        "stage": "STAGE1_8_LIVE_PILOT",
        "objective_version": "candidate_2obj",
        "model": "deepseek-flash",
        "temperature": 0,
        "thinking": "disabled",
        "rate_version": "deepseek-flash-2026-10-peak-conservative-v1",
        "environment": "ALFWorld TextWorld",
        "split": "valid_train",
        "horizon": 30,
        "manifest_sha256": mf_sha,
        "task_indices": TASK_INDICES,
        "frozen_tasks": tasks,
        "genome": G1,
        "runtime_variants": RUNTIMES,
        "budget_caps": {"episodes_max": 6, "physical_http_cap": 200,
                        "estimated_cost_cap_usd": 0.04, "scope": "batch total"},
        "shuffle_seed": SHUFFLE_SEED,
        "prompt_template": "STAGE1_8_GROUNDED_PROMPT_V1",
    }

    rng = random.Random(SHUFFLE_SEED)
    matrix = []
    order = 0
    for t in tasks:
        rts = list(RUNTIMES)
        rng.shuffle(rts)
        for rt in rts:
            order += 1
            matrix.append({
                "exec_order": order, "task_index": t["task_index"],
                "runtime_variant": rt, "genome_id": "G1",
                "game_id": t["game_id"],
                "episode_id": f"t{t['task_index']}_{rt}",
            })
    assert len(matrix) == 6

    (OUT / "experiment_config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "experiment_matrix.json").write_text(json.dumps(
        {"n_episodes": 6, "shuffle_seed": SHUFFLE_SEED, "combinations": matrix},
        indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "preregistration.json").write_text(json.dumps({
        "gates": {
            "GATE1_SOLVABILITY": "PASS if grounded has >=1 native won",
            "GATE2_RELATIVE": "grounded_only_wins / current_only_wins / both",
            "GATE3_COST": "report means; cost_per_success undefined if 0 wins",
            "GATE4_PLANNING_BEHAVIOR": "auxiliary only",
        },
        "decision_types": [
            "GROUNDED_SOLVABILITY_SIGNAL_OBSERVED",
            "AB_INCONCLUSIVE",
            "GROUNDED_SOLVABILITY_NOT_ESTABLISHED",
            "OFFLINE_BLOCKED",
            "SAFETY_STOP",
        ],
        "note": "3 debug tasks; exploratory only — not paper generalization",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "prompt_template_manifest.json").write_text(json.dumps({
        "version": "STAGE1_8_GROUNDED_PROMPT_V1",
        "frozen": True,
        "current": "legacy Stage 1 prompt (unchanged)",
        "grounded_planner_v1": "legacy + Active Subgoal + World Facts + Legal Action Candidates",
        "no_expert_injection": True,
        "no_extra_llm_calls": True,
        "llm_chooses_final_action": True,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("manifest", mf_sha)
    for m in matrix:
        print(f"  {m['exec_order']} t{m['task_index']} {m['runtime_variant']}")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
