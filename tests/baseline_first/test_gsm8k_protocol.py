"""GSM8K protocol integrity tests (Stage 3.0-P1-R2A-R1 Task 5).

Search/validation use official TRAIN tasks only; official TEST tasks are
held out and never feed evolutionary selection.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_protocol import (
    FINAL_TEST_INDICES,
    GSM8K_TEST_SIZE,
    GSM8K_TRAIN_SIZE,
    MAX_PHYSICAL_REQUESTS,
    MAX_TOTAL_COST_USD,
    MODEL_ID,
    MODEL_VERSION,
    PRICE_VERIFIED_AT,
    PROVIDER_BASE_URL,
    PROXY_POLICY,
    SEARCH_TRAIN_INDICES,
    VALIDATION_TRAIN_INDICES,
    budget_identity,
    protocol,
    split_manifest,
    make_test_task_id,
    make_train_task_id,
    write_artifacts,
)


def test_search_and_test_use_different_official_splits():
    m = split_manifest()
    assert m["search_uses_split"] == "train"
    assert m["test_uses_split"] == "test"
    assert m["selection_uses_official_test_set"] is False
    # ids literally name different splits
    assert all(i.startswith("gsm8k-train-") for i in m["search_task_ids"])
    assert all(i.startswith("gsm8k-train-") for i in m["validation_task_ids"])
    assert all(i.startswith("gsm8k-test-") for i in m["test_task_ids"])


def test_no_overlap_and_indices_in_range():
    s, v, t = set(SEARCH_TRAIN_INDICES), set(VALIDATION_TRAIN_INDICES), set(FINAL_TEST_INDICES)
    assert not (s & v)
    assert max(s) < GSM8K_TRAIN_SIZE
    assert max(t) < GSM8K_TEST_SIZE
    m = split_manifest()
    assert m["overlap_search_test"] == []
    assert m["overlap_validation_test"] == []
    assert m["overlap_search_validation"] == []


def test_split_hash_deterministic():
    assert split_manifest()["split_sha256"] == split_manifest()["split_sha256"]
    assert len(split_manifest()["split_sha256"]) == 64


def test_budget_caps():
    b = budget_identity()
    assert b["model_id"] == "deepseek-flash"
    assert b["model_version"] == "DeepSeek-V4.1-Flash"
    assert b["price_verified_at"] == "2026-10-16"
    assert b["max_physical_requests"] == 300
    assert b["max_total_cost_usd"] == 5.00
    assert b["worst_case_cost_peak_usd"] < 5.0
    assert b["limits_are_caps_not_targets"] is True
    assert b["retries_counted_in_ledger"] is True


def test_proxy_policy_and_base_url():
    b = budget_identity()
    assert b["proxy_policy"]["deepseek_physical_requests"] == "DIRECT_NO_SYSTEM_PROXY"
    assert b["provider_base_url"] == "https://api.deepseek.com"


def test_protocol_freezes_no_test_in_selection():
    p = protocol()
    assert p["no_test_set_in_selection"] is True
    assert p["no_test_set_driven_search_adjustment"] is True
    assert p["status"] == "FROZEN_NOT_EXECUTED"
    assert p["real_llm_calls"] == 0


def test_write_artifacts(tmp_path, monkeypatch):
    import src.benchmark.gsm8k_protocol as sp
    monkeypatch.setattr(sp, "OUT", tmp_path)
    sp.write_artifacts()
    saved = json.loads((tmp_path / "micro_pilot_protocol.json").read_text(encoding="utf-8"))
    assert saved["split"]["selection_uses_official_test_set"] is False
    assert saved["real_llm_calls"] == 0
