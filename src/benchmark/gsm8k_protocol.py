"""Frozen GSM8K protocol for the $5 micro-pilot (Task 5, R1 final fix).

CRITICAL CORRECTION vs earlier draft:
  Evolutionary selection must NEVER use the official GSM8K **test** set.
  Official split is:
      train: 7473 problems  -> search + validation (evolution only)
      test:  1319 problems  -> final held-out evaluation ONLY

This module is offline. It does not download data and does not call any API.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "stage3_0_p1_r2a_r1"

# Official GSM8K sizes
GSM8K_TRAIN_SIZE = 7473
GSM8K_TEST_SIZE = 1319

# Evolution sees ONLY the TRAIN split.
SEARCH_TRAIN_INDICES = list(range(0, 20))       # 20 train tasks for selection
VALIDATION_TRAIN_INDICES = list(range(20, 30))  # 10 train tasks for in-loop validation
# Final evaluation sees ONLY the official TEST split — never selection.
FINAL_TEST_INDICES = list(range(0, 20))         # 20 official test tasks, held out

# Index numbers may coincide across splits (train 0-19 vs test 0-19 are
# different problems). Identity is the prefixed task id, not the raw index.
assert not set(SEARCH_TRAIN_INDICES) & set(VALIDATION_TRAIN_INDICES)
assert max(SEARCH_TRAIN_INDICES) < GSM8K_TRAIN_SIZE
assert max(VALIDATION_TRAIN_INDICES) < GSM8K_TRAIN_SIZE
assert max(FINAL_TEST_INDICES) < GSM8K_TEST_SIZE


def make_train_task_id(index: int) -> str:
    return f"gsm8k-train-{index:04d}"


def make_test_task_id(index: int) -> str:
    return f"gsm8k-test-{index:04d}"


def split_manifest() -> Dict[str, Any]:
    search = [make_train_task_id(i) for i in SEARCH_TRAIN_INDICES]
    val = [make_train_task_id(i) for i in VALIDATION_TRAIN_INDICES]
    test = [make_test_task_id(i) for i in FINAL_TEST_INDICES]
    blob = json.dumps({"search": search, "validation": val, "test": test}, sort_keys=True)
    return {
        "benchmark": "GSM8K",
        "official_train_size": GSM8K_TRAIN_SIZE,
        "official_test_size": GSM8K_TEST_SIZE,
        "search_task_ids": search,
        "validation_task_ids": val,
        "test_task_ids": test,
        "n_search": len(search),
        "n_validation": len(val),
        "n_test": len(test),
        "search_uses_split": "train",
        "validation_uses_split": "train",
        "test_uses_split": "test",
        "selection_uses_official_test_set": False,
        "overlap_search_test": sorted(set(search) & set(test)),
        "overlap_validation_test": sorted(set(val) & set(test)),
        "overlap_search_validation": sorted(set(search) & set(val)),
        "split_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "note": (
            "Evolutionary selection and in-loop validation use ONLY official "
            "GSM8K train tasks. Official test tasks are scored once at the end "
            "and never feed selection or search strategy."
        ),
    }


MODEL_ID = "deepseek-flash"
MODEL_VERSION = "DeepSeek-V4.1-Flash"
PRICE_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"
PRICE_VERIFIED_AT = "2026-10-16"

MAX_INPUT_TOKENS_PER_REQUEST = 2000
MAX_OUTPUT_TOKENS_PER_REQUEST = 500
MAX_TOTAL_INPUT_TOKENS = 2_000_000
MAX_TOTAL_OUTPUT_TOKENS = 200_000
MAX_PHYSICAL_REQUESTS = 300
MAX_TOTAL_COST_USD = 5.00

PROVIDER_BASE_URL = "https://api.deepseek.com"
PROXY_POLICY = {
    "deepseek_physical_requests": "DIRECT_NO_SYSTEM_PROXY",
    "detail": (
        "DeepSeek HTTP calls ignore HTTP_PROXY/HTTPS_PROXY/ALL_PROXY and connect "
        "straight to api.deepseek.com. The Provider Gateway budget gate and the "
        "Docker execution sandbox keep their own separate security boundaries; "
        "direct connectivity does not bypass either of them."
    ),
}


def budget_identity() -> Dict[str, Any]:
    from src.runtime.provider_gateway import estimate_cost

    worst = estimate_cost(MODEL_ID, MAX_TOTAL_INPUT_TOKENS, MAX_TOTAL_OUTPUT_TOKENS, peak=True)
    return {
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "pricing_source": PRICE_SOURCE,
        "price_verified_at": PRICE_VERIFIED_AT,
        "max_input_tokens_per_request": MAX_INPUT_TOKENS_PER_REQUEST,
        "max_output_tokens_per_request": MAX_OUTPUT_TOKENS_PER_REQUEST,
        "max_total_input_tokens": MAX_TOTAL_INPUT_TOKENS,
        "max_total_output_tokens": MAX_TOTAL_OUTPUT_TOKENS,
        "max_physical_requests": MAX_PHYSICAL_REQUESTS,
        "max_total_cost_usd": MAX_TOTAL_COST_USD,
        "worst_case_cost_peak_usd": worst,
        "worst_case_under_cap": worst < MAX_TOTAL_COST_USD,
        "retries_counted_in_ledger": True,
        "provider_base_url": PROVIDER_BASE_URL,
        "proxy_policy": PROXY_POLICY,
        "limits_are_caps_not_targets": True,
    }


def protocol() -> Dict[str, Any]:
    return {
        "evidence_class": "HYPOTHESIS_ONLY",
        "status": "FROZEN_NOT_EXECUTED",
        "real_llm_calls": 0,
        "real_api_cost_usd": 0,
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "price_verified_at": PRICE_VERIFIED_AT,
        "split": split_manifest(),
        "budget": budget_identity(),
        "initial_workflow": "frozen official GSM8K round_1 template (AFlow archive)",
        "search_rounds": 3,
        "max_candidates": 3,
        "record_every_candidate": True,
        "verify_mutation_executable": True,
        "no_test_set_in_selection": True,
        "no_test_set_driven_search_adjustment": True,
        "stop_conditions": ["budget_cap", "billing_blocked", "crash_keep_partial"],
    }


def write_artifacts() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    split = split_manifest()
    budget = budget_identity()
    prot = protocol()
    (OUT / "micro_pilot_protocol.json").write_text(json.dumps(prot, indent=2), encoding="utf-8")
    return {"split": split, "budget": budget, "protocol": prot}


if __name__ == "__main__":
    out = write_artifacts()
    print(json.dumps({
        "split_sha256": out["split"]["split_sha256"],
        "search_uses": out["split"]["search_uses_split"],
        "test_uses": out["split"]["test_uses_split"],
        "selection_uses_official_test_set": out["split"]["selection_uses_official_test_set"],
        "worst_case_cost": out["budget"]["worst_case_cost_peak_usd"],
    }, indent=2))
