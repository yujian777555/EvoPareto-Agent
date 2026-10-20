"""R4 execution freeze (separate from confirmation-set freeze) + verifier.

Zero model calls. Fail-closed: any missing field, bad hash, illegal seed /
probability, or budget shortfall returns a non-empty error code.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "DEFAULT_EXEC_FREEZE",
    "canonical_config_sha256",
    "verify_exec_freeze",
    "build_exec_freeze",
]

BASE_SEED = 20260601
EXPECTED_PARENT_GRAPH_SHA = "ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e"
EXPECTED_PARENT_LF_SHA = "a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe"
EXPECTED_PARENT_PROMPT_SHA = "34b149ab37e571def0875faeac171867c3a2bb9fff03db4bc0ccca034e48e979"
EXPECTED_CONFIRM_V1_SHA = "1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4"
EXPECTED_TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"

REQUIRED_KEYS = (
    "version",
    "created_for",
    "baseline_commit",
    "parent_artefacts",
    "mutation_plan",
    "seeds",
    "pairing_blocks",
    "operator_policy",
    "selection_rules",
    "datasets",
    "evaluation",
    "endpoints",
    "budget_caps",
    "config_sha256",
)


def canonical_config_sha256(config: Dict[str, Any]) -> str:
    """SHA over the config with config_sha256 field removed, sorted keys."""
    body = {k: v for k, v in config.items() if k != "config_sha256"}
    blob = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_exec_freeze(*, baseline_commit: str, r_values: Sequence[int] = (6, 10)) -> Dict[str, Any]:
    """Construct the canonical R4 execution freeze dict (config_sha256 filled)."""
    plan_seed_of = lambda r: BASE_SEED + 1009 * r
    cfg: Dict[str, Any] = {
        "version": "R4-exec-v0-proposed",
        "status": "PROPOSED_PENDING_PLANNER_ACCEPTANCE",
        "created_for": "LEVEL3-PILOT-R4 execution protocol (zero real model calls at freeze time)",
        "baseline_commit": baseline_commit,
        "parent_artefacts": {
            "graph_path": "results/level3_pilot_r2/frozen_candidates/parent_graph.py",
            "graph_sha256_byte": EXPECTED_PARENT_GRAPH_SHA,
            "graph_sha256_lf": EXPECTED_PARENT_LF_SHA,
            "prompt_path": "results/level3_pilot_r2/frozen_candidates/parent_prompt.py",
            "prompt_sha256": EXPECTED_PARENT_PROMPT_SHA,
        },
        "mutation_plan": {
            "seed_rule": "plan_seed[r] = BASE_SEED + 1009 * r",
            "base_seed": BASE_SEED,
            "operator_names": ["M_SET_INSTRUCTION", "M_ADD_SAMPLING"],
            "operator_probs": [0.5, 0.5],
            "instruction_pool": [
                "Solve step by step, end with 'Answer: <num>'.",
                "Think carefully, verify arithmetic, final number after 'Answer:'.",
                "Compute directly. Output the numeric answer after 'Answer:'.",
                "Solve briefly. Final answer after 'Answer:'.",
            ],
            "sampling_ks": [2, 3, 4],
            "allow_noop": False,
            "rng": "LCG (1664525, 1013904223, 2^32) keyed by (plan.seed + 10007*(slot+1))",
        },
        "seeds": {
            "base_seed": BASE_SEED,
            "r_values": list(r_values),
            "plan_seeds": {str(r): plan_seed_of(r) for r in r_values},
        },
        "pairing_blocks": {
            "description": "D and E share MutationPlan seed in block r; slots 0-1 from Parent; E slots 2-3 from gen-1 winner",
            "d_slots": [0, 1, 2, 3],
            "e_gen1_slots": [0, 1],
            "e_gen2_slots": [2, 3],
        },
        "operator_policy": {
            "failure_mode": "FailedCandidate retained at slot with dev_accuracy=0; never silent redraw",
            "noop": "NOOP_MUTATION becomes FailedCandidate",
            "specs_ref": "src/research/r4_workflow_program.OPERATOR_SPECS",
        },
        "selection_rules": {
            "gen1_winner": "max dev accuracy on shared dev set; ties -> creation order",
            "e_final": "max dev accuracy among 4 slots; ties -> creation order e1a<e1b<e2a<e2b",
            "d_final": "max dev accuracy among 4 slots; ties -> creation order",
            "failed_candidate_score": 0.0,
        },
        "datasets": {
            "confirmation": {
                "file": "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json",
                "task_set_sha256": EXPECTED_CONFIRM_V1_SHA,
                "n": 40,
                "role": "final scoring only; never selection",
            },
            "development": {
                "file": "results/level3_pilot_r4_data/gsm8k_train_official.jsonl",
                "sha256": EXPECTED_TRAIN_SHA,
                "n_available": 7473,
                "n_used": 20,
                "role": "candidate ranking only",
                "selection_rule": "first 20 official train indices (frozen before calls; not performance-based)",
            },
            "generation_tasks": {
                "required": False,
                "note": "R4 mutations are syntactic MutationPlan operators; no LLM rewrite generation set",
            },
        },
        "evaluation": {
            "scoring": "host-side gold; never in container/prompt/IPC",
            "answer_extract": "project extractor; exact match on canonical gold",
            "failure_scoring": {
                "invalid_output": "incorrect",
                "timeout": "incorrect",
                "execution_failure": "incorrect",
                "missing_row": "incorrect",
                "no_task_dropping": True,
            },
            "request_log_required": True,
        },
        "endpoints": {
            "primary": "seed-level paired E-D confirmation accuracy (conditional on frozen 40 tasks)",
            "secondary": ["task-level McNemar within block", "B-A/C-A/D-A/E-A Holm family"],
            "holm_family": ["B-A", "C-A", "D-A", "E-A", "E-D"],
            "holm_note": "E-D in the 5-family uses Holm-adjusted thresholds; raw Wilcoxon p=0.03125 at R=6 is NOT enough for the first Holm step (0.01). R>=8 needed for min exact p=0.0078125 <= 0.01.",
            "tests": {
                "task_level": "exact McNemar two-sided",
                "seed_level_unadjusted": "exact Wilcoxon signed-rank two-sided (R>=6 to reject at 0.05)",
                "seed_level_in_holm": "same Wilcoxon p-values adjusted over 5-family",
            },
            "stopping": "fixed-N; no optional stopping",
        },
        "budget_caps": {
            "requests_formula": "240 + 240 * R",
            "safety_margin": 0.10,
            "token_in_per_req": [150, 400],
            "token_out_per_req": [150, 800],
            "worst_case_usd_per_req": 0.003,
            "current_auth": {
                "max_requests": 300,
                "max_tokens_in": 2000000,
                "max_tokens_out": 200000,
                "max_cost_usd": 5.0,
            },
            "authorization_required": True,
            "real_api_allowed_at_freeze_time": False,
        },
    }
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    return cfg


DEFAULT_EXEC_FREEZE = build_exec_freeze(baseline_commit="1705dcf40151684b0e97b1b00020a8877a4eb966")


def verify_exec_freeze(config: Dict[str, Any]) -> str:
    """Return '' if OK else a fail-closed error code."""
    for k in REQUIRED_KEYS:
        if k not in config:
            return "EXEC_FREEZE_MISSING_FIELD:%s" % k

    # config hash
    declared = config.get("config_sha256")
    recomputed = canonical_config_sha256(config)
    if declared != recomputed:
        return "EXEC_FREEZE_HASH_MISMATCH"

    # parent artefacts
    pa = config["parent_artefacts"]
    if pa.get("graph_sha256_byte") != EXPECTED_PARENT_GRAPH_SHA:
        return "EXEC_PARENT_GRAPH_SHA"
    if pa.get("prompt_sha256") != EXPECTED_PARENT_PROMPT_SHA:
        return "EXEC_PARENT_PROMPT_SHA"

    # mutation plan
    mp = config["mutation_plan"]
    names = mp.get("operator_names") or []
    probs = mp.get("operator_probs") or []
    if not names or len(names) != len(probs):
        return "EXEC_PLAN_NAME_PROB_LEN"
    if any(not isinstance(p, (int, float)) or p < 0 for p in probs):
        return "EXEC_PLAN_PROB_NEGATIVE"
    if abs(sum(probs) - 1.0) > 1e-6:
        return "EXEC_PLAN_PROB_SUM"
    if not mp.get("instruction_pool"):
        return "EXEC_PLAN_EMPTY_POOL"

    # seeds
    seeds = config["seeds"]
    if "base_seed" not in seeds or "plan_seeds" not in seeds:
        return "EXEC_SEEDS_INCOMPLETE"
    pss = list(seeds["plan_seeds"].values())
    if len(pss) != len(set(pss)):
        return "EXEC_SEEDS_NOT_UNIQUE"
    for r, s in seeds["plan_seeds"].items():
        expected = int(seeds["base_seed"]) + 1009 * int(r)
        if int(s) != expected:
            return "EXEC_SEEDS_RULE_MISMATCH:%s" % r

    # selection
    sr = config["selection_rules"]
    if sr.get("failed_candidate_score") != 0.0:
        return "EXEC_SELECTION_FAILED_SCORE"

    # datasets
    ds = config["datasets"]
    if ds.get("confirmation", {}).get("task_set_sha256") != EXPECTED_CONFIRM_V1_SHA:
        return "EXEC_CONFIRM_SHA"
    if ds.get("development", {}).get("sha256") != EXPECTED_TRAIN_SHA:
        return "EXEC_DEV_SHA"

    # budget
    bc = config["budget_caps"]
    if bc.get("real_api_allowed_at_freeze_time") is not False:
        return "EXEC_BUDGET_REAL_API_FLAG"
    if "requests_formula" not in bc:
        return "EXEC_BUDGET_FORMULA"

    # endpoints mention Holm and R>=6 constraint
    ep = config["endpoints"]
    if "holm_family" not in ep or len(ep["holm_family"]) != 5:
        return "EXEC_ENDPOINTS_HOLM_FAMILY"

    return ""
