"""Frozen GSM8K task split + budget identity for the $5 micro-pilot (Task 3).

Rules:
  - search/validation tasks drive evolutionary selection ONLY
  - official test tasks are held out and never used as selection evidence
  - task IDs are hash-locked so the split cannot drift silently
  - DeepSeek physical requests must bypass the system global proxy and go
    direct to api.deepseek.com (gateway keeps its own security boundary)

This module is offline: it does not download data and does not call any API.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results" / "stage3_0_p1_r2a"

# ---------------------------------------------------------------------------
# GSM8K official test set (1319 problems, index 0..1318)
# Pilot uses a deterministic slice. Split is FIXED and hash-locked below.
# ---------------------------------------------------------------------------
GSM8K_TEST_SET_SIZE = 1319
SEARCH_TASK_INDICES = list(range(0, 20))       # 20 tasks for evolution selection
VALIDATION_TASK_INDICES = list(range(20, 30))  # 10 tasks for in-loop validation
TEST_TASK_INDICES = list(range(30, 50))        # 20 tasks held out for final eval

assert not set(SEARCH_TASK_INDICES) & set(TEST_TASK_INDICES)
assert not set(VALIDATION_TASK_INDICES) & set(TEST_TASK_INDICES)
assert not set(SEARCH_TASK_INDICES) & set(VALIDATION_TASK_INDICES)


def task_id(index: int) -> str:
    """Stable synthetic task identity for GSM8K official test index."""
    return f"gsm8k-test-{index:04d}"


def split_manifest() -> Dict[str, Any]:
    search = [task_id(i) for i in SEARCH_TASK_INDICES]
    val = [task_id(i) for i in VALIDATION_TASK_INDICES]
    test = [task_id(i) for i in TEST_TASK_INDICES]
    blob = json.dumps({"search": search, "validation": val, "test": test}, sort_keys=True)
    return {
        "benchmark": "GSM8K",
        "source": "official GSM8K test set indices (data downloaded at pilot time)",
        "search_task_ids": search,
        "validation_task_ids": val,
        "test_task_ids": test,
        "n_search": len(search),
        "n_validation": len(val),
        "n_test": len(test),
        "overlap_search_test": sorted(set(search) & set(test)),
        "overlap_validation_test": sorted(set(val) & set(test)),
        "overlap_search_validation": sorted(set(search) & set(val)),
        "split_sha256": hashlib.sha256(blob.encode("utf-8")).hexdigest(),
        "selection_uses_test_set": False,
        "note": (
            "Evolutionary selection sees ONLY search+validation tasks. "
            "Test tasks are scored once at the end and never feed selection."
        ),
    }


# ---------------------------------------------------------------------------
# Budget / model identity (must match provider_gateway.PRICE_TABLE)
# ---------------------------------------------------------------------------
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
        "DeepSeek HTTP calls must ignore the system/global proxy (no HTTP_PROXY/"
        "HTTPS_PROXY/ALL_PROXY) and connect straight to api.deepseek.com. "
        "The Provider Gateway and the code-execution sandbox keep their own "
        "separate security boundaries."
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
    }


def write_artifacts() -> Dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    split = split_manifest()
    budget = budget_identity()
    (OUT / "gsm8k_split_manifest.json").write_text(json.dumps(split, indent=2), encoding="utf-8")
    (OUT / "budget_identity.json").write_text(json.dumps(budget, indent=2), encoding="utf-8")
    return {"split": split, "budget": budget}


if __name__ == "__main__":
    out = write_artifacts()
    print(json.dumps({
        "split_sha256": out["split"]["split_sha256"],
        "n_search": out["split"]["n_search"],
        "n_test": out["split"]["n_test"],
        "overlaps": out["split"]["overlap_search_test"],
        "worst_case_cost": out["budget"]["worst_case_cost_peak_usd"],
        "under_cap": out["budget"]["worst_case_under_cap"],
    }, indent=2))
