"""Task B tests: persistence fault protection, no conditional skips."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationIntegrityError,
    AuthorizationMissing,
    AuthorizationRecord,
    BudgetExceeded,
)

SECRET = "r23b-secret"


def _caps(**kw):
    base = {"max_physical": 20, "max_cost_usd": 1.0,
            "max_total_in": 80000, "max_total_out": 5000}
    base.update(kw)
    return base


def test_settle_persist_failure_blocks_new_instance(tmp_path):
    """os.replace failure during settle_actual: marker blocks a new instance."""
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-b1",
        caps=_caps(max_cost_usd=0.05), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="SETFAIL1",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected os.replace failure")
        return real_replace(src, dst)

    os.replace = flaky
    try:
        with pytest.raises(Exception):
            led.settle_actual(physical_id="SETFAIL1", actual_in=1, actual_out=1,
                              observed_cost=0.50, http_status=200,
                              model_returned="m", finish_reason="stop")
    finally:
        os.replace = real_replace

    # in-process poison
    assert getattr(rec, "_poisoned", "")
    # durable fault marker present
    fault = tmp_path / "authorization_record.json.PERSIST_FAULT"
    assert fault.exists(), "fault marker must be written on persist failure"
    # NEW instance refuses to load
    with pytest.raises(AuthorizationIntegrityError, match="PERSIST_FAULT"):
        AuthorizationRecord.open_existing(
            tmp_path / "authorization_record.json", secret_key=SECRET
        )
    # cannot auto-create a new authorization over the fault
    with pytest.raises(Exception):
        AuthorizationRecord.create(
            tmp_path / "authorization_record.json", auth_id="new",
            caps=_caps(), secret_key=SECRET,
        )
    led.close()


def test_marker_write_failure_reports_protection_not_persistable(tmp_path):
    """If BOTH record and marker writes fail, the system must say so loudly."""
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-b2",
        caps=_caps(), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="MKFAIL01",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)

    real_replace = os.replace
    real_write_text = Path.write_text

    def flaky_replace(src, dst):
        raise OSError("disk full (replace)")

    def flaky_write_text(self, *a, **k):
        if "PERSIST_FAULT" in str(self):
            raise OSError("disk full (marker)")
        return real_write_text(self, *a, **k)

    os.replace = flaky_replace
    Path.write_text = flaky_write_text
    try:
        with pytest.raises(Exception) as ei:
            led.settle_actual(physical_id="MKFAIL01", actual_in=1, actual_out=1,
                              observed_cost=0.01, http_status=200,
                              model_returned="m", finish_reason="stop")
        msg = str(ei.value)
        assert "PROTECTION_NOT_PERSISTABLE" in msg or "PERSIST_FAILED" in str(getattr(rec, "_poisoned", ""))
    finally:
        os.replace = real_replace
        Path.write_text = real_write_text
    # the in-process poison records BOTH failures
    assert "NEITHER_RECORD_NOR_FAULT_MARKER_WRITABLE" in str(getattr(rec, "_poisoned", "")) or \
           "PROTECTION_NOT_PERSISTABLE" in msg
    led.close()


def test_no_conditional_skip_on_core_safety():
    """Core safety invariants must never be optional skips."""
    src = (ROOT / "tests" / "baseline_first" / "test_r22_cross_process_persist.py").read_text(encoding="utf-8")
    assert "pytest.skip" not in src, "core safety tests must not use conditional skip"


def test_actual_usage_evidence_kept_on_settle_failure(tmp_path):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-b3",
        caps=_caps(max_cost_usd=0.05), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="EVID0001",
                phase="opt", prompt_sha="s", res_in=5, res_out=5, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="EVID0001", actual_in=5, actual_out=5,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    rows = led.request_rows()
    row = [r for r in rows if r["physical_request_id"] == "EVID0001"][0]
    assert row["actual_tokens_in"] == 5
    assert row["actual_tokens_out"] == 5
    assert row["observed_cost_usd"] == 0.50
    led.close()


def test_unsettled_reservations_survive_restart(tmp_path):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-b4",
        caps=_caps(), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L1", physical_id="SURVIVE1",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.05)
    led.close()
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    snap = rec2.snapshot_flat()
    assert snap["outstanding_reserved_cost_usd"] == pytest.approx(0.05)
    assert snap["reserved_tokens_in"] == 10
