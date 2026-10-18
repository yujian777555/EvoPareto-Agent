"""Phase-2 blocker regression tests (5 fixes). Offline, no real DeepSeek."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    STATE_RESERVED,
    STATE_SETTLED_ACTUAL,
    STATE_SETTLED_UNKNOWN_BLOCKED,
    AuthBudgetLedger,
    AuthorizationRecord,
    BudgetExceeded,
    DuplicatePhysicalRequest,
    UnifiedBudgetGate,
    UnknownBillingBlocked,
)

SECRET = "phase2-secret"


def _caps(**kw):
    base = {"max_physical": 10, "max_cost_usd": 1.0, "max_total_in": 80000, "max_total_out": 5000}
    base.update(kw)
    return base


def _mk(tmp_path, **kw):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-p2",
        caps=_caps(**kw), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    return rec, led


# ---------- Fix 1: events initialized before auth-missing handler ----------
def test_production_main_events_initialized_on_missing_auth(tmp_path):
    import importlib.util

    path = ROOT / "scripts" / "level3_live_calibration" / "run_live_calibration.py"
    spec = importlib.util.spec_from_file_location("live_cal_p2", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # point OUT at an empty dir so auth is missing
    mod.OUT = tmp_path / "empty_out"
    mod.OUT.mkdir()
    rc = mod.main()
    assert rc == 3, "missing authorization must return the fail-closed code"
    summary = json.loads((mod.OUT / "live_run_summary.json").read_text(encoding="utf-8"))
    assert summary["STOP_REASON"] == "AUTHORIZATION_RECORD_MISSING"


# ---------- Fix 2: crash recovery blocks unknown billing ----------
def test_crash_recovery_blocks_stale_reservations(tmp_path):
    rec, led = _mk(tmp_path)
    # simulate a crash: reserve but never settle
    led.reserve(run_id="r", logical_id="L", physical_id="CRASH0001",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.05)
    led.close()
    # "restart": new working DB, same record
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    led2 = AuthBudgetLedger(tmp_path / "work2.sqlite", rec2)
    # rehydrate put a placeholder; the stale RESERVED row is in work.sqlite only.
    # To simulate a real crash window we insert a RESERVED row into the new DB:
    led2._conn.execute(
        "INSERT INTO requests (physical_request_id, auth_id, run_id, logical_request_id, "
        "request_phase, prompt_sha256, state, reserved_tokens_in, reserved_tokens_out, "
        "reserved_cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("CRASH0001", rec2.auth_id, "r", "L", "opt", "s", STATE_RESERVED, 10, 10, 0.05, 0),
    )
    led2._conn.commit()
    n = led2.recover_stale_reservations()
    assert n == 1
    snap = led2.snapshot()
    assert snap["blocked"] is True
    assert "CRASH_RECOVERY" in str(snap["block_reason"])
    led2.close()


# ---------- Fix 3: settle validates hard budget on actuals ----------
def test_settle_actual_exceeding_cost_cap_blocks(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.10)
    led.reserve(run_id="r", logical_id="L", physical_id="OVERCST01",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.05)
    with pytest.raises(BudgetExceeded, match="ACTUAL_COST_EXCEEDS_CAP"):
        led.settle_actual(physical_id="OVERCST01", actual_in=10, actual_out=10,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    assert snap["blocked"] is True
    led.close()


def test_settle_actual_exceeding_token_cap_blocks(tmp_path):
    rec, led = _mk(tmp_path, max_total_out=100)
    led.reserve(run_id="r", logical_id="L", physical_id="OVEROUT01",
                phase="opt", prompt_sha="s", res_in=10, res_out=50, res_cost=0.01)
    with pytest.raises(BudgetExceeded, match="ACTUAL_OUTPUT_TOKENS_EXCEED_CAP"):
        led.settle_actual(physical_id="OVEROUT01", actual_in=10, actual_out=500,
                          observed_cost=0.01, http_status=200,
                          model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    assert snap["blocked"] is True
    led.close()


# ---------- Fix 4: legacy migration source separation ----------
def test_legacy_migration_refuses_runtime_ledger(tmp_path):
    """A live runtime ledger written by this run must not be double-imported."""
    rec, led = _mk(tmp_path)
    # write a runtime ledger that looks like the live one
    runtime = tmp_path / "request_ledger.json"
    runtime.write_text(json.dumps({
        "rows": [
            {"physical_request_id": "AAA", "usage_prompt_tokens": 81, "usage_completion_tokens": 227, "observed_cost_usd": 0.0003},
            {"physical_request_id": "BBB", "usage_prompt_tokens": 81, "usage_completion_tokens": 227, "observed_cost_usd": 0.0003},
        ]
    }), encoding="utf-8")
    # the production helper looks for the SEALED legacy name
    sealed = tmp_path / "legacy_request_ledger_level3.json"
    assert not sealed.exists()
    # runtime ledger is NOT auto-ingested
    from src.runtime.auth_ledger import open_production_authorization
    rec2 = open_production_authorization(
        tmp_path / "authorization_record.json", secret_key=SECRET,
        legacy_ledger=sealed if sealed.exists() else None,
    )
    assert rec2.consumed["physical_attempts"] == 0
    led.close()


def test_legacy_sealed_file_imported_once(tmp_path):
    import shutil

    sealed = tmp_path / "legacy_request_ledger_level3.json"
    shutil.copy2(ROOT / "results/level3_live_calibration/request_ledger.json", sealed)
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-l",
        caps=_caps(), secret_key=SECRET,
    )
    rec.migrate_legacy_level3(sealed)
    rec.migrate_legacy_level3(sealed)
    assert rec.consumed["physical_attempts"] == 2
    assert rec.consumed["actual_tokens_in"] == 162
    assert rec.consumed["actual_tokens_out"] == 454


# ---------- Fix 5: record-level physical-id uniqueness + snapshot ----------
def test_physical_id_unique_across_working_dbs(tmp_path):
    rec, led = _mk(tmp_path)
    led.reserve(run_id="r", logical_id="L", physical_id="GLOBALID1",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    led2 = AuthBudgetLedger(tmp_path / "work2.sqlite", rec2)
    with pytest.raises(DuplicatePhysicalRequest):
        led2.reserve(run_id="r2", logical_id="L2", physical_id="GLOBALID1",
                     phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led2.close()


def test_snapshot_consistent_after_mixed_lifecycle(tmp_path):
    rec, led = _mk(tmp_path)
    led.reserve(run_id="r", logical_id="L1", physical_id="SNAPAAAA",
                phase="opt", prompt_sha="s", res_in=100, res_out=50, res_cost=0.01)
    led.reserve(run_id="r", logical_id="L2", physical_id="SNAPBBBB",
                phase="opt", prompt_sha="s", res_in=100, res_out=50, res_cost=0.01)
    led.settle_actual(physical_id="SNAPAAAA", actual_in=10, actual_out=5,
                      observed_cost=0.001, http_status=200,
                      model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    assert snap["physical_attempts"] == 2
    assert snap["actual_tokens_in"] == 10
    assert snap["reserved_tokens_in"] == 100  # second still outstanding
    assert snap["outstanding_reserved_cost_usd"] == pytest.approx(0.01)
    assert snap["spent_cost_usd"] == pytest.approx(0.001)
    led.close()
