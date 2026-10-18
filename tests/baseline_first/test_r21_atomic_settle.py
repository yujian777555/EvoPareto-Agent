"""Task A tests: single-lock settle atomicity, persistence failure, concurrency."""
from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationRecord,
    BudgetExceeded,
    DuplicateSettlement,
)

SECRET = "r21a-secret"


def _caps(**kw):
    base = {"max_physical": 20, "max_cost_usd": 1.0,
            "max_total_in": 80000, "max_total_out": 5000}
    base.update(kw)
    return base


def _mk(tmp_path, **kw):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-r21a",
        caps=_caps(**kw), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    return rec, led


def test_over_cap_settle_persists_block_and_actual_evidence(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="ATOMIC001",
                phase="opt", prompt_sha="s", res_in=5, res_out=5, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="ATOMIC001", actual_in=5, actual_out=5,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    # block persisted
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    assert rec2._body["blocked"] is True
    # actual usage evidence retained in the history tail
    tail = rec2._body.get("history_tail") or []
    block_entries = [h for h in tail if h.get("kind") == "BLOCK_ON_SETTLE"]
    assert block_entries, "actual usage evidence must be in the audit trail"
    assert block_entries[-1]["actual_in"] == 5
    assert block_entries[-1]["observed_cost"] == 0.50
    # reservation released (not leaked)
    snap = rec2.snapshot_flat()
    assert snap["outstanding_reserved_cost_usd"] == 0.0
    led.close()


def test_over_cap_settle_does_not_release_other_reservations(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.10)
    led.reserve(run_id="r", logical_id="L1", physical_id="KEEPAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.03)
    led.reserve(run_id="r", logical_id="L2", physical_id="KEEPBBBB",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.03)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="KEEPAAAA", actual_in=1, actual_out=1,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    # the OTHER reservation must still be outstanding
    assert snap["outstanding_reserved_cost_usd"] == pytest.approx(0.03)
    assert snap["reserved_tokens_in"] == 1
    led.close()


def test_single_lock_no_race_with_concurrent_reserve(tmp_path):
    """Over-limit settlement and a new reservation race: the new one must be blocked."""
    rec, led = _mk(tmp_path, max_cost_usd=0.10, max_physical=100)
    led.reserve(run_id="r", logical_id="L1", physical_id="RACEAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.05)
    errors = []
    ok_reserve = []

    def settle_over():
        try:
            led.settle_actual(physical_id="RACEAAAA", actual_in=1, actual_out=1,
                              observed_cost=0.50, http_status=200,
                              model_returned="m", finish_reason="stop")
        except Exception as e:
            errors.append(f"settle:{type(e).__name__}")

    def reserve_new():
        try:
            led.reserve(run_id="r", logical_id="L2", physical_id="RACEBBBB",
                        phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
            ok_reserve.append(1)
        except Exception as e:
            errors.append(f"reserve:{type(e).__name__}")

    t1 = threading.Thread(target=settle_over)
    t2 = threading.Thread(target=reserve_new)
    t1.start(); t2.start()
    t1.join(); t2.join()
    # after the over-limit settle, the block must be persisted
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    # either the reserve happened before the block (and was counted) or was
    # refused. What must NOT happen: reserve succeeds AFTER the block was
    # persisted without being counted.
    assert rec2._body["blocked"] is True
    if ok_reserve:
        # if a reserve landed, it must be reflected in the consumed counter
        assert rec2.consumed["physical_attempts"] >= 2
    led.close()


def test_persistence_failure_injection_block_not_lost(tmp_path):
    """If persist() throws after the mutator set blocked, the block must not be lost."""
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="PERSIST01",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)

    # inject a failure inside the REAL _persist by breaking os.replace
    import os as _os

    real_replace = _os.replace
    calls = {"n": 0}

    def flaky_replace(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected disk failure")
        return real_replace(src, dst)

    _os.replace = flaky_replace
    try:
        with pytest.raises(Exception):
            rec.mutate(lambda b: b.update({"blocked": True, "block_reason": "INJECTED"}))
    finally:
        _os.replace = real_replace
    # persistence failure poisons the record: all further ops are fail-closed
    assert getattr(rec, "_poisoned", ""), "record must be poisoned after persist failure"
    with pytest.raises(Exception, match="POISONED|PERSIST_FAILED|INTEGRITY"):
        rec.mutate(lambda b: None)
    led.close()


def test_settle_actual_records_usage_even_on_over_cap(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="USAGE0001",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="USAGE0001", actual_in=42, actual_out=77,
                          observed_cost=0.99, http_status=200,
                          model_returned="deepseek-flash", finish_reason="stop")
    rows = led.request_rows()
    row = [r for r in rows if r["physical_request_id"] == "USAGE0001"][0]
    assert row["actual_tokens_in"] == 42
    assert row["actual_tokens_out"] == 77
    assert row["observed_cost_usd"] == 0.99
    led.close()


def test_duplicate_settlement_still_rejected(tmp_path):
    rec, led = _mk(tmp_path)
    led.reserve(run_id="r", logical_id="L", physical_id="DUPSET01",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.settle_actual(physical_id="DUPSET01", actual_in=1, actual_out=1,
                      observed_cost=0.001, http_status=200,
                      model_returned="m", finish_reason="stop")
    with pytest.raises(DuplicateSettlement):
        led.settle_actual(physical_id="DUPSET01", actual_in=1, actual_out=1,
                          observed_cost=0.001, http_status=200,
                          model_returned="m", finish_reason="stop")
    led.close()
