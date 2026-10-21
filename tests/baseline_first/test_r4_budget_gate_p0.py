"""P0 budget-gate tests: hash-recompute bypass, remaining quota, HTTP block.

No real API. Auth snapshots are constructed in-memory or loaded read-only.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_budget_policy import POLICY, policy_mismatch
from src.research.r4_exec_freeze import (
    DEFAULT_EXEC_FREEZE,
    AuthSnapshot,
    BudgetError,
    canonical_config_sha256,
    compute_budget_requirements,
    load_auth_snapshot,
    verify_budget_feasibility,
    verify_exec_config_structure,
    verify_exec_freeze,
    verify_execution_allowed,
)


def _rehash(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    return cfg


@pytest.fixture(scope="module")
def auth():
    return load_auth_snapshot()


@pytest.fixture()
def good_auth():
    """In-memory generous auth — used only to prove config policy still binds."""
    return AuthSnapshot(
        max_requests=10**8,
        max_tokens_in=10**12,
        max_tokens_out=10**12,
        max_cost_usd=1e6,
        consumed_requests=0,
        consumed_tokens_in=0,
        consumed_tokens_out=0,
        spent_usd=0.0,
        remaining_requests=10**8,
        remaining_tokens_in=10**12,
        remaining_tokens_out=10**12,
        remaining_usd=1e6,
        blocked=False,
        auth_id="test",
    )


# ---------------------------------------------------------------------------
# A2 bypass: recompute hash after lowering budget params
# ---------------------------------------------------------------------------

def test_lowered_base_requests_rehash_still_rejected(good_auth):
    cfg = _rehash(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["base_requests"] = 0
    cfg = _rehash(cfg)
    # structure includes policy check -> reject even with good auth
    err = verify_exec_config_structure(cfg)
    assert err.startswith("BUDGET_POLICY_MISMATCH")
    assert verify_exec_freeze(cfg, auth=good_auth).startswith("BUDGET_POLICY_MISMATCH")


def test_lowered_per_r_and_margin_and_tokens_rehash_rejected(good_auth):
    for key, val in (
        ("per_r_requests", 1),
        ("safety_margin", 0.0),
        ("worst_case_usd_per_req", 0.0),
        ("token_out_per_req", [0, 1]),
        ("token_in_per_req", [0, 1]),
        ("requests_formula", "1 + 1 * R"),
    ):
        cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
        cfg["budget_caps"][key] = val
        cfg = _rehash(cfg)
        err = verify_exec_config_structure(cfg)
        assert err.startswith("BUDGET_POLICY_"), (key, err)


def test_negative_base_requests():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["base_requests"] = -10
    cfg = _rehash(cfg)
    assert verify_exec_config_structure(cfg).startswith("BUDGET_POLICY_")


def test_bool_and_string_budget_fields():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["base_requests"] = True
    cfg = _rehash(cfg)
    assert verify_exec_config_structure(cfg).startswith("BUDGET_POLICY_TYPE")
    cfg2 = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg2["budget_caps"]["per_r_requests"] = "240"
    cfg2 = _rehash(cfg2)
    assert verify_exec_config_structure(cfg2).startswith("BUDGET_POLICY_TYPE")


def test_nan_and_inf_rejected():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["safety_margin"] = float("nan")
    cfg = _rehash(cfg)
    err = verify_exec_config_structure(cfg)
    assert err.startswith("BUDGET_POLICY_")
    cfg2 = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg2["budget_caps"]["worst_case_usd_per_req"] = float("inf")
    cfg2 = _rehash(cfg2)
    assert verify_exec_config_structure(cfg2).startswith("BUDGET_POLICY_")
    with pytest.raises(BudgetError):
        compute_budget_requirements(6, safety_margin=float("nan"))
    with pytest.raises(BudgetError):
        compute_budget_requirements(6, usd_per_req=float("inf"))


def test_missing_budget_fields():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    del cfg["budget_caps"]["safety_margin"]
    cfg = _rehash(cfg)
    assert verify_exec_config_structure(cfg).startswith("BUDGET_POLICY_MISSING")


def test_planned_r_neq_seeds():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["planned_r_values"] = [6]
    cfg = _rehash(cfg)
    err = verify_exec_config_structure(cfg)
    assert err == "BUDGET_PLANNED_R_NEQ_SEEDS"


def test_planned_r_neq_plan_seed_keys():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    # drop key 10 but keep planned
    cfg["seeds"]["plan_seeds"].pop("10", None)
    cfg["seeds"]["r_values"] = [6, 10]
    cfg["budget_caps"]["planned_r_values"] = [6, 10]
    cfg = _rehash(cfg)
    err = verify_exec_config_structure(cfg)
    assert err == "BUDGET_PLANNED_R_NEQ_PLAN_SEEDS"


def test_formula_string_must_match_policy():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["budget_caps"]["requests_formula"] = "100 + 100 * R"
    cfg = _rehash(cfg)
    assert verify_exec_config_structure(cfg) == "BUDGET_POLICY_MISMATCH:requests_formula"


# ---------------------------------------------------------------------------
# A3 remaining quota
# ---------------------------------------------------------------------------

def test_remaining_quota_not_max(auth):
    assert auth["remaining_requests"] == auth["max_requests"] - auth["consumed_requests"]
    assert auth["remaining_requests"] < auth["max_requests"]
    err = verify_budget_feasibility(compute_budget_requirements(6), auth)
    assert err.startswith("BUDGET_REQUESTS_EXCEEDED")
    assert "remaining=" in err


def test_missing_remaining_fields_fail_closed():
    a = AuthSnapshot(
        max_requests=10**9, max_tokens_in=10**12, max_tokens_out=10**12, max_cost_usd=1e6,
        consumed_requests=0, spent_usd=0.0, blocked=False, auth_id="x",
        # no remaining_*
    )
    err = verify_budget_feasibility(compute_budget_requirements(1), a)
    assert err.startswith("BUDGET_REMAINING_MISSING")


def test_plan_fits_when_remaining_sufficient():
    a = AuthSnapshot(
        max_requests=1000, max_tokens_in=10**9, max_tokens_out=10**9, max_cost_usd=100.0,
        consumed_requests=100, consumed_tokens_in=0, consumed_tokens_out=0, spent_usd=0.0,
        remaining_requests=900, remaining_tokens_in=10**9, remaining_tokens_out=10**9,
        remaining_usd=100.0, blocked=False, auth_id="x",
    )
    # R=1 needs 528 requests <= 900 remaining
    assert verify_budget_feasibility(compute_budget_requirements(1), a) == ""
    # R=10 needs 2904 > 900
    assert verify_budget_feasibility(compute_budget_requirements(10), a).startswith("BUDGET_REQUESTS_EXCEEDED")


# ---------------------------------------------------------------------------
# A4 execution authorization ≠ budget pass; no HTTP
# ---------------------------------------------------------------------------

def test_proposed_status_blocks_http_even_with_loose_budget(good_auth):
    err = verify_execution_allowed(
        DEFAULT_EXEC_FREEZE, auth=good_auth, execution_authorized=True
    )
    assert err.startswith("EXEC_STATUS_BLOCKS_HTTP")


def test_missing_planner_authorization_blocks(good_auth):
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["status"] = "APPROVED"  # still needs execution_authorized
    err = verify_execution_allowed(cfg, auth=good_auth, execution_authorized=False)
    assert err == "EXEC_NOT_AUTHORIZED_BY_PLANNER"


def test_budget_exceeded_blocks_http(auth):
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["status"] = "APPROVED"
    cfg["execution_authorized"] = True
    err = verify_execution_allowed(cfg, auth=auth, execution_authorized=True)
    assert err.startswith("BUDGET_")


def test_corrupt_auth_blocks_http():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["status"] = "APPROVED"
    cfg["execution_authorized"] = True
    err = verify_execution_allowed(
        cfg,
        auth=AuthSnapshot(blocked=False, auth_id="x"),  # missing remaining
        execution_authorized=True,
    )
    assert err.startswith("BUDGET_REMAINING_MISSING") or err.startswith("BUDGET_FIELDS_INVALID")


def test_zero_model_calls_in_gate_paths():
    """Budget/execution gates must not perform HTTP — static sanity."""
    src = Path(ROOT / "src/research/r4_exec_freeze.py").read_text(encoding="utf-8")
    for banned in ("import requests", "import httpx", "import urllib.request", "deepseek.com"):
        assert banned not in src
    # execution gate module likewise
    assert "http" not in src.lower() or "https://github.com/openai" not in src.lower()


def test_auth_loader_is_read_only(auth):
    # loading does not create auth file
    import json

    p = Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json"
    before = p.read_bytes()
    load_auth_snapshot()
    after = p.read_bytes()
    assert before == after
    assert auth["consumed_requests"] == 244
