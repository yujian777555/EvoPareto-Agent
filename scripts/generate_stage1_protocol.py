"""Generate Stage 1 frozen experiment config + matrix + preregistration.

Reads the real manifest, verifies task identities, writes immutable config.
No API calls. Run once BEFORE any live episode.
"""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/native_alfworld/development_task_pool.json"
OUT = ROOT / "results/stage1_feasibility"

TASK_INDICES = [0, 10, 20]
SEEDS = [11, 23]

GENOMES = [
    {
        "id": "G1",
        "label": "pilot1_baseline",
        "planner_strategy": "cot",
        "memory_strategy": "short_term",
        "reflection_strategy": "self_critique",
        "tool_policy": "balanced",
        "reasoning_budget": 64,
    },
    {
        "id": "G2",
        "label": "longer_memory_planning_prompt",
        "planner_strategy": "plan_and_solve",
        "memory_strategy": "episodic",
        "reflection_strategy": "none",
        "tool_policy": "conservative",
        "reasoning_budget": 64,
    },
    {
        "id": "G3",
        "label": "lightweight_cost",
        "planner_strategy": "direct",
        "memory_strategy": "none",
        "reflection_strategy": "none",
        "tool_policy": "no_tools",
        "reasoning_budget": 16,
    },
]

SHUFFLE_SEED = 2026  # fixed, declared before any run


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = MANIFEST.read_bytes()
    mf_sha = hashlib.sha256(raw).hexdigest()
    mf = json.loads(raw.decode("utf-8"))
    tasks = mf["tasks"]

    frozen_tasks = []
    for idx in TASK_INDICES:
        t = tasks[idx]
        gid = str(t["game_id"])
        parts = gid.split("/")
        ttype = parts[-2] if len(parts) >= 2 else ""
        frozen_tasks.append(
            {
                "task_index": idx,
                "game_id": gid,
                "fingerprint": t.get("fingerprint"),
                "task_type_dir": ttype,
                "task_type": ttype.split("-")[0] if "-" in ttype else ttype,
            }
        )

    config = {
        "stage": "STAGE1_FEASIBILITY",
        "objective_version": "candidate_2obj",
        "objective_names": ["performance", "cost"],
        "maximize": [True, False],
        "performance_source": "native_won",
        "cost_source": "tokens x frozen peak-conservative rates",
        "model": "deepseek-flash",
        "rate_version": "deepseek-flash-2026-10-peak-conservative-v1",
        "environment": "ALFWorld TextWorld",
        "split": "valid_train",
        "horizon": 30,
        "manifest_path": str(MANIFEST.relative_to(ROOT)).replace("\\", "/"),
        "manifest_sha256": mf_sha,
        "task_indices": TASK_INDICES,
        "frozen_tasks": frozen_tasks,
        "seeds": SEEDS,
        "genomes": GENOMES,
        "budget_caps": {
            "episodes_max": 18,
            "physical_http_cap": 650,
            "estimated_cost_cap_usd": 0.11,
            "scope": "batch total, not per-episode",
        },
        "rates": {"input_cache_miss_per_1m": 0.30, "output_per_1m": 1.20},
        "temperature": "not set (provider default); seed does not force determinism",
        "shuffle_seed": SHUFFLE_SEED,
    }

    # Build 18-cell matrix: for each (task, seed) block shuffle genome order
    rng = random.Random(SHUFFLE_SEED)
    matrix: List[Dict[str, Any]] = []
    order = 0
    for t in frozen_tasks:
        for seed in SEEDS:
            gids = [g["id"] for g in GENOMES]
            rng.shuffle(gids)
            for gid in gids:
                order += 1
                matrix.append(
                    {
                        "exec_order": order,
                        "task_index": t["task_index"],
                        "genome_id": gid,
                        "seed": seed,
                        "game_id": t["game_id"],
                        "episode_id": f"t{t['task_index']}_{gid}_s{seed}",
                    }
                )

    assert len(matrix) == 18
    combos = [(m["task_index"], m["genome_id"], m["seed"]) for m in matrix]
    assert len(set(combos)) == 18, "matrix must have 18 unique combinations"

    prereg = {
        "title": "Stage 1 Genome Solvability & Multi-objective Signal Feasibility",
        "frozen_before_results": True,
        "design": "3 tasks x 3 genomes x 2 seeds = 18 episodes",
        "gates": {
            "GATE1_SOLVABILITY": {
                "PASS": "at least 1 episode with native won=true among the 18",
                "FAIL": "all won=false",
                "on_fail": [
                    "do not expand to 36",
                    "do not start five-arm evolution",
                    "do not claim PEEM/PPEC ineffective",
                    "diagnose solvability via DecisionLog",
                ],
            },
            "GATE2_GENOME_DISTINGUISHABILITY": {
                "PASS_DESCRIPTIVE": (
                    "at least two paired (task_index, seed) blocks show differing "
                    "won outcomes across genomes (pre-registered descriptive screen; "
                    "NOT a KS p-value criterion)"
                ),
                "COST_ONLY": (
                    "if won identical across genomes and only cost/length differ: "
                    "call it cost distinguishability, NOT performance improvement"
                ),
                "INCONCLUSIVE": "insufficient sample for either claim",
            },
            "GATE3_MULTIOBJECTIVE_SIGNAL": {
                "PASS": (
                    ">=1 real success AND >=2 non-dominated (performance, cost) "
                    "genome-level aggregates with meaningful tradeoff"
                ),
                "DEGENERATE": "all performance = 0",
                "INCONCLUSIVE": "single unstable success",
                "rule": "cheaper failure is NOT better performance",
            },
        },
        "final_decision_rule": {
            "GATE1_FAIL": "STOP / SOLVABILITY_DIAGNOSIS",
            "GATE1_PASS_GATE2_OR_3_INCONCLUSIVE": "REVIEW / NO AUTOMATIC EXPANSION",
            "GATE1_3_SUPPORT": "REQUEST STAGE 2 APPROVAL",
        },
        "prohibitions": [
            "no second batch of episodes",
            "no extra genomes after results",
            "no task re-selection after results",
            "no parameter changes after results",
            "no PEEM/PPEC modification",
            "no five-arm evolution in Stage 1",
            "no progress-proxy as formal performance",
            "no silent auto-retry of failed episodes",
        ],
    }

    (OUT / "experiment_config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "experiment_matrix.json").write_text(
        json.dumps(
            {
                "n_episodes": len(matrix),
                "shuffle_seed": SHUFFLE_SEED,
                "order_rule": "within each (task_index, seed) block, genome order is "
                              "shuffled by random.Random(SHUFFLE_SEED)",
                "combinations": matrix,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (OUT / "preregistration.json").write_text(
        json.dumps(prereg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("manifest_sha256", mf_sha)
    print("matrix size", len(matrix))
    for m in matrix:
        print(f"  {m['exec_order']:2d}  task={m['task_index']:2d}  {m['genome_id']}  seed={m['seed']}")
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
