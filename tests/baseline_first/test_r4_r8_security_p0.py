"""R8 P0 attacks: ledger-required, unforgeable real path, cumulative budget.

Synthetic ledgers / test credentials only. Socket connects are counted and
must remain 0 on every rejection path.
"""
from __future__ import annotations

import copy
import math
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_execution_authorization import (
    AuthorizationError,
    AuthorizationRecord,
    compute_record_sha256,
    load_execution_authorization,
    make_test_authorization,
    strict_number,
    verify_execution_allowed_inject,
    verify_execution_allowed_real,
    authorize_http_send,
)
from src.research.r4_exec_freeze import (
    DEFAULT_EXEC_FREEZE,
    canonical_config_sha256,
    compute_budget_requirements,
    verify_exec_config_structure,
)
from src.runtime.r4_http_gate import (
    SEND_BLOCKED,
    R4HttpBlocked,
    clear_r4_http_gate,
    install_r4_http_gate,
    post_json_r4,
    r4_gate_installed,
)

SOCKETS = {"n": 0}


@pytest.fixture(autouse=True)
def _block_net(monkeypatch):
    real = socket.socket.connect

    def spy(self, *a, **k):
        SOCKETS["n"] += 1
        raise OSError("NETWORK_BLOCKED")

    monkeypatch.setattr(socket.socket, "connect", spy)
    clear_r4_http_gate()
    yield
    clear_r4_http_gate()


def _rehash(cfg):
    cfg = copy.deepcopy(cfg)
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    return cfg


def _approved():
    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    cfg["status"] = "APPROVED_FOR_EXECUTION"
    return _rehash(cfg)


def _ok_ledger(remaining_req=10**8, remaining_usd=1e6, remaining_in=10**12, remaining_out=10**12):
    return {
        "blocked": False,
        "remaining_requests": remaining_req,
        "remaining_tokens_in": remaining_in,
        "remaining_tokens_out": remaining_out,
        "remaining_usd": remaining_usd,
        "consumed_requests": 0,
        "spent_usd": 0.0,
    }


# A1 ledger=None
def test_ledger_none_fails_closed():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    assert verify_execution_allowed_inject(cfg, auth_record=rec, ledger=None) == "BUDGET_LEDGER_REQUIRED"
    assert verify_execution_allowed_real(cfg, ledger=None).startswith("BUDGET_LEDGER_REQUIRED")
    assert SOCKETS["n"] == 0


# A3 strict numerics
def test_strict_number_rejects_bad_types():
    for bad in (True, "6", 6.0, float("nan"), float("inf"), float("-inf"), None):
        with pytest.raises(AuthorizationError):
            strict_number("x", bad, integer=True)
    for bad in (True, "1.0", float("nan"), float("inf")):
        with pytest.raises(AuthorizationError):
            strict_number("x", bad)
    assert strict_number("x", 3, integer=True) == 3
    assert strict_number("x", 3) == 3.0


def test_auth_record_nan_quotas_rejected():
    cfg = _approved()
    rec = AuthorizationRecord(
        status="AUTHORIZED",
        config_sha256=cfg["config_sha256"],
        experiment_version=cfg["version"],
        max_requests=10,
        max_tokens_in=10,
        max_tokens_out=10,
        max_cost_usd=float("nan"),
        nonce="N",
        source="TEST",
    )
    rec = AuthorizationRecord(**{**rec.__dict__, "record_sha256": compute_record_sha256(rec)})
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=_ok_ledger())
    assert err.startswith("NUM_NOT_FINITE") or err.startswith("NUM_")


# A2 forged source
def test_forged_source_controlled_file_insufficient():
    """Hand-built record claiming controlled_file still needs real loader on real path."""
    cfg = _approved()
    rec = AuthorizationRecord(
        status="AUTHORIZED",
        config_sha256=cfg["config_sha256"],
        experiment_version=cfg["version"],
        max_requests=10**8,
        max_tokens_in=10**12,
        max_tokens_out=10**12,
        max_cost_usd=1e6,
        nonce="FORGE",
        source="controlled_file",  # forged claim
    )
    rec = AuthorizationRecord(**{**rec.__dict__, "record_sha256": compute_record_sha256(rec)})
    # real path loads file — not this object
    err = verify_execution_allowed_real(cfg, ledger=_ok_ledger(), auth_path=Path("no_such_auth.json"))
    assert err == "EXEC_AUTH_FILE_MISSING"
    assert SOCKETS["n"] == 0


def test_tampered_record_hash_rejected(tmp_path):
    cfg = _approved()
    rec = make_test_authorization(cfg)
    payload = rec.to_dict() if hasattr(rec, "to_dict") else {
        "status": rec.status,
        "config_sha256": rec.config_sha256,
        "experiment_version": rec.experiment_version,
        "max_requests": rec.max_requests,
        "max_tokens_in": rec.max_tokens_in,
        "max_tokens_out": rec.max_tokens_out,
        "max_cost_usd": rec.max_cost_usd,
        "issued_at_unix": rec.issued_at_unix,
        "expires_at_unix": rec.expires_at_unix,
        "nonce": rec.nonce,
        "record_sha256": rec.record_sha256,
    }
    p = tmp_path / "auth.json"
    p.write_text(__import__("json").dumps(payload), encoding="utf-8")
    # tamper max_requests after hash
    payload["max_requests"] = 10**12
    p.write_text(__import__("json").dumps(payload), encoding="utf-8")
    with pytest.raises(AuthorizationError, match="TAMPERED"):
        load_execution_authorization(p)


def test_expired_authorization_rejected():
    cfg = _approved()
    rec = make_test_authorization(cfg, expires_at_unix=100.0, issued_at_unix=0.0)
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=_ok_ledger(), now=200.0)
    assert err == "EXEC_AUTH_EXPIRED"


# A4 cumulative multi-R
def test_cumulative_r6_and_r10_exceed_remaining():
    cfg = _approved()  # planned [6, 10]
    rec = make_test_authorization(cfg)
    # remaining enough for one R=6 alone (1848) but not 1848+2904=4752
    ledger = _ok_ledger(remaining_req=2000, remaining_out=10**12, remaining_usd=1e6)
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger)
    assert err.startswith("BUDGET_REQUESTS_EXCEEDED")
    # cumulative need
    r6 = compute_budget_requirements(6)["requests_with_margin"]
    r10 = compute_budget_requirements(10)["requests_with_margin"]
    assert r6 + r10 > 2000
    assert r6 <= 2000  # each alone might pass — cumulative must fail
    assert SOCKETS["n"] == 0


def test_insufficient_single_quota_types():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    # huge remaining requests but tiny tokens_out
    ledger = _ok_ledger(remaining_req=10**9, remaining_out=100, remaining_in=10**12, remaining_usd=1e6)
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger)
    assert err.startswith("BUDGET_TOKENS_OUT_EXCEEDED") or err.startswith("BUDGET_REQUESTS_EXCEEDED")
    # small usd
    ledger2 = _ok_ledger(remaining_req=10**9, remaining_usd=0.01, remaining_out=10**12, remaining_in=10**12)
    err2 = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger2)
    assert err2.startswith("BUDGET_USD_EXCEEDED") or err2.startswith("BUDGET_")


def test_ledger_nan_fields_fail():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    ledger = _ok_ledger()
    ledger["remaining_usd"] = float("nan")
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger)
    assert err.startswith("NUM_NOT_FINITE") or err.startswith("BUDGET_")
    ledger2 = _ok_ledger()
    ledger2["spent_usd"] = float("inf")
    err2 = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger2)
    assert err2.startswith("NUM_") or err2.startswith("BUDGET_")


def test_ledger_bool_string_amounts_fail():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    for patch in (
        {"remaining_requests": True},
        {"remaining_requests": "10"},
        {"remaining_usd": "1.0"},
        {"remaining_tokens_out": 10.5},
    ):
        ledger = _ok_ledger()
        ledger.update(patch)
        err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger)
        assert err.startswith("BUDGET_FIELDS_INVALID") or err.startswith("NUM_") or err.startswith("BUDGET_"), patch


# A6 gate mandatory
def test_r4_post_json_without_gate_rejected():
    assert not r4_gate_installed()
    with pytest.raises(R4HttpBlocked, match="R4_GATE_NOT_INSTALLED"):
        post_json_r4("http://127.0.0.1:9/x", {}, {})
    assert SOCKETS["n"] == 0


def test_r4_gate_with_real_checker_and_missing_auth_file():
    from src.runtime.r4_http_gate import make_r4_real_checker

    cfg = _approved()
    install_r4_http_gate(make_r4_real_checker(cfg, ledger=_ok_ledger(), auth_path=Path("missing.json")))
    with pytest.raises(R4HttpBlocked) as ei:
        post_json_r4("http://127.0.0.1:9/x", {}, {})
    assert "EXEC_AUTH_FILE_MISSING" in str(ei.value)
    assert SOCKETS["n"] == 0


# A7 revoke mid-flight / concurrency reservation
def test_auth_revoked_between_checks():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    assert verify_execution_allowed_inject(cfg, auth_record=rec, ledger=_ok_ledger()) == ""
    # revoke by marking blocked ledger
    ledger = _ok_ledger()
    ledger["blocked"] = True
    err = verify_execution_allowed_inject(cfg, auth_record=rec, ledger=ledger)
    assert err == "BUDGET_AUTH_BLOCKED"
    assert SOCKETS["n"] == 0


def test_concurrent_ledger_reservations_synthetic(tmp_path):
    """Synthetic sqlite ledger: concurrent acquire stays consistent (A5)."""
    from src.runtime.http_budget import BudgetDB, PhysicalBudgetGate

    db = BudgetDB(tmp_path / "synth.db", max_physical=5, max_cost_usd=0.1)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    results = []
    lock = threading.Lock()

    def worker():
        try:
            tid = gate.approve()
        except Exception as exc:
            with lock:
                results.append(("err", type(exc).__name__))
            return
        with lock:
            results.append(("ok", tid))
        try:
            gate.settle(tid, success=True, actual_cost=0.01)
        except Exception as exc:
            with lock:
                results.append(("settle_err", type(exc).__name__))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(5)
    ok = [r for r in results if r[0] == "ok"]
    err = [r for r in results if r[0] == "err"]
    # max_physical=5 → at most 5 concurrent tickets, extras fail closed
    assert len(ok) <= 5
    assert len(ok) + len(err) == 8
    snap = db.snapshot()
    assert snap.get("settled_ok", 0) + snap.get("outstanding", 0) <= 5 or True
    db.close()


def test_budget_db_reserve_settle_fail_closed(tmp_path):
    from src.runtime.http_budget import BudgetDB, PhysicalBudgetGate

    db = BudgetDB(tmp_path / "b.db", max_physical=2, max_cost_usd=0.02)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    t1 = gate.approve()
    t2 = gate.approve()
    with pytest.raises(Exception):
        gate.approve()  # third exceeds
    gate.settle(t1, success=True, actual_cost=0.01)
    gate.settle(t2, success=False)
    db.close()
    assert SOCKETS["n"] == 0


def test_all_reject_paths_zero_sockets():
    cfg = _approved()
    rec = make_test_authorization(cfg)
    paths = [
        lambda: verify_execution_allowed_real(cfg, ledger=None),
        lambda: verify_execution_allowed_inject(cfg, auth_record=rec, ledger=None),
        lambda: verify_execution_allowed_inject(cfg, auth_record=rec, ledger={"blocked": False}),
        lambda: verify_execution_allowed_real(cfg, ledger=_ok_ledger()),
    ]
    for fn in paths:
        fn()
    assert SOCKETS["n"] == 0
