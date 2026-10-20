"""Tests for R4 execution freeze verifier (fail-closed)."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_exec_freeze import (
    DEFAULT_EXEC_FREEZE,
    canonical_config_sha256,
    verify_exec_freeze,
)


def test_default_freeze_verifies():
    assert verify_exec_freeze(DEFAULT_EXEC_FREEZE) == ""
    assert DEFAULT_EXEC_FREEZE["config_sha256"] == canonical_config_sha256(DEFAULT_EXEC_FREEZE)


def test_freeze_file_on_disk_verifies():
    import json

    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v0_proposed.json"
    if not p.exists():
        pytest.skip("freeze file absent")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert verify_exec_freeze(cfg) == ""


def test_missing_field_fails():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    del cfg["mutation_plan"]
    assert verify_exec_freeze(cfg).startswith("EXEC_FREEZE_MISSING_FIELD")


def test_hash_tamper_fails():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["baseline_commit"] = "deadbeef"
    assert verify_exec_freeze(cfg) == "EXEC_FREEZE_HASH_MISMATCH"


def test_seed_rule_mismatch_fails():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["seeds"]["plan_seeds"]["6"] = 12345
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg).startswith("EXEC_SEEDS_RULE_MISMATCH")


def test_duplicate_seeds_fail():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    vals = list(cfg["seeds"]["plan_seeds"].values())
    cfg["seeds"]["plan_seeds"]["6"] = vals[1]
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg) == "EXEC_SEEDS_NOT_UNIQUE"


def test_prob_sum_fails():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["mutation_plan"]["operator_probs"] = [0.3, 0.3]
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg) == "EXEC_PLAN_PROB_SUM"


def test_confirm_sha_fails():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["datasets"]["confirmation"]["task_set_sha256"] = "0" * 64
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg) == "EXEC_CONFIRM_SHA"


def test_real_api_flag_must_be_false():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["real_api_allowed_at_freeze_time"] = True
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg) == "EXEC_BUDGET_REAL_API_FLAG"


def test_holm_family_required():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["endpoints"]["holm_family"] = ["B-A"]
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    assert verify_exec_freeze(cfg) == "EXEC_ENDPOINTS_HOLM_FAMILY"


def test_v1_confirmation_freeze_not_rewritten():
    import json

    p = ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    assert cfg["task_set_sha256"] == "1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4"
    assert "budget_caps" not in cfg  # execution config not stuffed into v1
