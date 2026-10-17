"""GSM8K split integrity + budget identity tests (Stage 3.0-P1-R2A-R1 Task 3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_split import (
    MAX_PHYSICAL_REQUESTS,
    MAX_TOTAL_COST_USD,
    MAX_TOTAL_INPUT_TOKENS,
    MAX_TOTAL_OUTPUT_TOKENS,
    MODEL_ID,
    MODEL_VERSION,
    PRICE_VERIFIED_AT,
    PROVIDER_BASE_URL,
    PROXY_POLICY,
    SEARCH_TASK_INDICES,
    TEST_TASK_INDICES,
    VALIDATION_TASK_INDICES,
    budget_identity,
    split_manifest,
    write_artifacts,
)


def test_search_and_test_are_disjoint():
    s = set(SEARCH_TASK_INDICES)
    t = set(TEST_TASK_INDICES)
    v = set(VALIDATION_TASK_INDICES)
    assert not (s & t), "search and test overlap"
    assert not (v & t), "validation and test overlap"
    assert not (s & v), "search and validation overlap"


def test_split_manifest_no_overlap_and_hashed():
    m = split_manifest()
    assert m["overlap_search_test"] == []
    assert m["overlap_validation_test"] == []
    assert m["overlap_search_validation"] == []
    assert m["selection_uses_test_set"] is False
    assert m["n_search"] == 20
    assert m["n_test"] == 20
    assert len(m["split_sha256"]) == 64
    # deterministic
    assert split_manifest()["split_sha256"] == m["split_sha256"]


def test_budget_identity_caps():
    b = budget_identity()
    assert b["model_id"] == "deepseek-flash"
    assert b["model_version"] == "DeepSeek-V4.1-Flash"
    assert b["price_verified_at"] == "2026-10-16"
    assert b["max_physical_requests"] == 300
    assert b["max_total_cost_usd"] == 5.00
    assert b["max_total_input_tokens"] == 2_000_000
    assert b["max_total_output_tokens"] == 200_000
    assert b["worst_case_cost_peak_usd"] < 5.0
    assert b["worst_case_under_cap"] is True
    assert b["retries_counted_in_ledger"] is True


def test_proxy_policy_direct_no_system_proxy():
    b = budget_identity()
    assert b["proxy_policy"]["deepseek_physical_requests"] == "DIRECT_NO_SYSTEM_PROXY"
    assert b["provider_base_url"] == "https://api.deepseek.com"


def test_gateway_http_path_disables_proxy():
    gw = (ROOT / "src" / "runtime" / "provider_gateway.py").read_text(encoding="utf-8")
    assert "ProxyHandler({})" in gw
    assert "build_opener" in gw


def test_write_artifacts(tmp_path, monkeypatch):
    import src.benchmark.gsm8k_split as sp
    monkeypatch.setattr(sp, "OUT", tmp_path)
    out = sp.write_artifacts()
    assert (tmp_path / "gsm8k_split_manifest.json").exists()
    assert (tmp_path / "budget_identity.json").exists()
    saved = json.loads((tmp_path / "gsm8k_split_manifest.json").read_text(encoding="utf-8"))
    assert saved["selection_uses_test_set"] is False
