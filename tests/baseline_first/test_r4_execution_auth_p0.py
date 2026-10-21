"""P0 R7: execution-authorization bypass attacks. HTTP count must stay 0."""
from __future__ import annotations

import copy
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_execution_authorization import (
    AuthorizationError,
    AuthorizationRecord,
    authorize_http_send,
    make_test_authorization,
    verify_execution_allowed_inject as verify_execution_allowed,
    verify_execution_allowed_real,
)
from src.research.r4_exec_freeze import (
    DEFAULT_EXEC_FREEZE,
    AuthSnapshot,
    canonical_config_sha256,
    verify_exec_config_structure,
)

# HTTP / network send counter — tests assert this stays 0
HTTP_SEND_COUNT = {"n": 0}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Count and block real socket connects."""
    real_connect = socket.socket.connect

    def spy(self, *a, **k):
        HTTP_SEND_COUNT["n"] += 1
        raise RuntimeError("NETWORK_FORBIDDEN_IN_TESTS")

    monkeypatch.setattr(socket.socket, "connect", spy)
    yield
    # count includes our spy raises; stays 0 successful sends


def _rehash(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    return cfg


def _approved(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["status"] = "APPROVED_FOR_EXECUTION"
    return _rehash(cfg)


@pytest.fixture()
def approved_cfg():
    return _approved(DEFAULT_EXEC_FREEZE)


@pytest.fixture()
def auth_for(cfg=None):
    def _make(config):
        return make_test_authorization(config)

    return _make


def test_default_proposed_blocks_even_with_authorized_record():
    rec = make_test_authorization(DEFAULT_EXEC_FREEZE)
    err = verify_execution_allowed(DEFAULT_EXEC_FREEZE, auth_record=rec, allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_STATUS_NOT_APPROVED")


def test_attack_base_requests_zero_rehash(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["budget_caps"]["base_requests"] = 0
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:BUDGET_POLICY_")
    assert HTTP_SEND_COUNT["n"] == 0


def test_attack_per_r_zero_rehash(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["budget_caps"]["per_r_requests"] = 0
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:BUDGET_POLICY_")


def test_attack_margin_tokens_cost_zero_rehash(approved_cfg, auth_for):
    for key, val in (
        ("safety_margin", 0.0),
        ("token_out_per_req", [0, 0]),
        ("token_in_per_req", [0, 0]),
        ("worst_case_usd_per_req", 0.0),
    ):
        cfg = copy.deepcopy(approved_cfg)
        cfg["budget_caps"][key] = val
        cfg = _rehash(cfg)
        err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
        assert err.startswith("EXEC_CONFIG_REJECTED:"), key


def test_attack_multi_param_rehash(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["budget_caps"]["base_requests"] = 1
    cfg["budget_caps"]["per_r_requests"] = 1
    cfg["budget_caps"]["safety_margin"] = 0.0
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:")


def test_attack_budget_change_without_rehash(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["budget_caps"]["base_requests"] = 1  # stale hash
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert "EXEC_CONFIG_REJECTED:EXEC_FREEZE_HASH_MISMATCH" == err or err.startswith("EXEC_CONFIG_REJECTED:EXEC_FREEZE_HASH_MISMATCH")


def test_attack_planned_r_empty_and_missing(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["budget_caps"]["planned_r_values"] = []
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:BUDGET_PLANNED_R_INVALID")

    cfg2 = copy.deepcopy(approved_cfg)
    del cfg2["budget_caps"]["planned_r_values"]
    cfg2 = _rehash(cfg2)
    err2 = verify_execution_allowed(cfg2, auth_record=auth_for(cfg2), allow_test_injection=True)
    assert err2.startswith("EXEC_CONFIG_REJECTED:")


def test_attack_illegal_r_types(approved_cfg, auth_for):
    for bad in (6.9, "6", True, None):
        cfg = copy.deepcopy(approved_cfg)
        cfg["budget_caps"]["planned_r_values"] = [bad]
        cfg = _rehash(cfg)
        err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
        assert err.startswith("EXEC_CONFIG_REJECTED:"), (bad, err)
        assert HTTP_SEND_COUNT["n"] == 0


def test_attack_base_seed_change_with_synced_derived(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["seeds"]["base_seed"] = 12345
    cfg["mutation_plan"]["base_seed"] = 12345
    cfg["seeds"]["plan_seeds"] = {"6": 12345 + 1009 * 6, "10": 12345 + 1009 * 10}
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:EXEC_SEEDS_BASE_MISMATCH")


def test_attack_undeclared_status_with_auth_flag(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["status"] = "SOME_NEW_STATUS"
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_STATUS_NOT_APPROVED")


def test_attack_auth_sha_mismatch(approved_cfg):
    rec = AuthorizationRecord(
        status="AUTHORIZED",
        config_sha256="0" * 64,
        experiment_version=approved_cfg["version"],
        max_requests=10**6,
        max_tokens_in=10**12,
        max_tokens_out=10**12,
        max_cost_usd=1e6,
        source="TEST",
    )
    err = verify_execution_allowed(approved_cfg, auth_record=rec, allow_test_injection=True)
    assert err == "EXEC_AUTH_CONFIG_SHA_MISMATCH"
    assert HTTP_SEND_COUNT["n"] == 0


def test_attack_missing_or_corrupt_auth(approved_cfg):
    assert verify_execution_allowed(approved_cfg, auth_record=None, allow_test_injection=True) == "EXEC_AUTH_MISSING"
    from src.research.r4_execution_authorization import compute_record_sha256

    bad = AuthorizationRecord(
        status="AUTHORIZED",
        config_sha256=approved_cfg["config_sha256"],
        experiment_version=approved_cfg["version"],
        max_requests=0,
        max_tokens_in=1,
        max_tokens_out=1,
        max_cost_usd=1.0,
        nonce="N",
        source="TEST",
    )
    bad = AuthorizationRecord(**{**bad.__dict__, "record_sha256": compute_record_sha256(bad)})
    err = verify_execution_allowed(approved_cfg, auth_record=bad, allow_test_injection=True)
    assert err.startswith("EXEC_AUTH_QUOTA_INVALID")



def test_attack_forge_loose_auth_not_used_on_real_path(approved_cfg):
    """Real path loads controlled file — caller objects are never used."""
    rec = make_test_authorization(approved_cfg)
    # real path with missing file
    err = verify_execution_allowed_real(approved_cfg, ledger={"blocked": False, "remaining_requests": 1, "remaining_tokens_in": 1, "remaining_tokens_out": 1, "remaining_usd": 1.0}, auth_path=Path("nope.json"))
    assert err == "EXEC_AUTH_FILE_MISSING"
    with pytest.raises(AuthorizationError):
        authorize_http_send(approved_cfg, ledger={"blocked": False, "remaining_requests": 1, "remaining_tokens_in": 1, "remaining_tokens_out": 1, "remaining_usd": 1.0}, auth_path=Path("nope.json"))
    assert HTTP_SEND_COUNT["n"] == 0


def test_attack_status_proposed_with_forge_auth():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)  # PROPOSED
    rec = make_test_authorization(cfg)
    err = verify_execution_allowed(cfg, auth_record=rec, allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_STATUS_NOT_APPROVED")



def test_attack_ledger_remaining_missing(approved_cfg):
    rec = make_test_authorization(approved_cfg)
    ledger = {"blocked": False}  # no remaining_*
    err = verify_execution_allowed(approved_cfg, auth_record=rec, ledger=ledger, allow_test_injection=True)
    assert err.startswith("BUDGET_REMAINING_MISSING")


def test_attack_ledger_blocked(approved_cfg):
    rec = make_test_authorization(approved_cfg)
    ledger = {
        "blocked": True,
        "remaining_requests": 10**8,
        "remaining_tokens_in": 10**12,
        "remaining_tokens_out": 10**12,
        "remaining_usd": 1e6,
    }
    err = verify_execution_allowed(approved_cfg, auth_record=rec, ledger=ledger, allow_test_injection=True)
    assert err == "BUDGET_AUTH_BLOCKED"


def test_authorize_http_send_raises_and_zero_network(approved_cfg):
    with pytest.raises(AuthorizationError):
        authorize_http_send(
            approved_cfg,
            ledger={"blocked": False, "remaining_requests": 10**8, "remaining_tokens_in": 10**12, "remaining_tokens_out": 10**12, "remaining_usd": 1e6},
            auth_path=Path("nope.json"),
        )
    assert HTTP_SEND_COUNT["n"] == 0



def test_config_cannot_embed_execution_flag(approved_cfg, auth_for):
    cfg = copy.deepcopy(approved_cfg)
    cfg["execution_authorized"] = True
    cfg = _rehash(cfg)
    err = verify_execution_allowed(cfg, auth_record=auth_for(cfg), allow_test_injection=True)
    assert err.startswith("EXEC_CONFIG_REJECTED:EXEC_AUTH_FIELD_FORBIDDEN_IN_CONFIG")


def test_structure_rejects_config_execution_flag():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["execution_authorized"] = True
    cfg = _rehash(cfg)
    assert verify_exec_config_structure(cfg) == "EXEC_AUTH_FIELD_FORBIDDEN_IN_CONFIG"
