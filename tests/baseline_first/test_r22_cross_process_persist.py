"""Task C: cross-process persistence-failure fail-closed tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationIntegrityError,
    AuthorizationRecord,
    BudgetExceeded,
)

SECRET = "r22c-secret"


def _caps(**kw):
    base = {"max_physical": 20, "max_cost_usd": 1.0,
            "max_total_in": 80000, "max_total_out": 5000}
    base.update(kw)
    return base


def test_persist_failure_poisons_then_new_instance_refuses(tmp_path):
    """After a persist failure, a NEW AuthorizationRecord must not silently continue."""
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-c",
        caps=_caps(max_cost_usd=0.05), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="PF000001",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)

    # inject os.replace failure during settle
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("injected persist failure")
        return real_replace(src, dst)

    os.replace = flaky
    try:
        with pytest.raises(Exception):
            led.settle_actual(physical_id="PF000001", actual_in=1, actual_out=1,
                              observed_cost=0.50, http_status=200,
                              model_returned="m", finish_reason="stop")
    finally:
        os.replace = real_replace

    # current object is poisoned
    assert getattr(rec, "_poisoned", "")
    with pytest.raises(Exception):
        rec.mutate(lambda b: None)

    # simulate process exit + new instance: the DISK record may still look
    # valid (the failed persist never landed). The new instance must NOT be
    # able to continue as if nothing happened — we require an explicit
    # fail-closed marker on disk.
    marker = tmp_path / "authorization_record.json.PERSIST_FAULT"
    # the implementation must leave a fault marker; if it does not, that is a
    # gap we surface rather than silently proceed.
    if marker.exists():
        with pytest.raises(Exception):
            AuthorizationRecord.open_existing(
                tmp_path / "authorization_record.json", secret_key=SECRET
            )
    else:
        # documented limitation: in-memory poison does not survive restart.
        # Fail-closed contract requires refusing real requests until manual
        # recovery — the caller must check _poisoned or the fault marker.
        # We assert the risk is RECORDED, not silently ignored.
        assert getattr(rec, "_poisoned", ""), "poison must at least be recorded in-process"
        # a naive reopen WOULD succeed — that is the gap; we mark it explicitly
        rec2 = AuthorizationRecord.open_existing(
            tmp_path / "authorization_record.json", secret_key=SECRET
        )
        # the reopened record has NOT been poisoned by the failed persist
        assert not getattr(rec2, "_poisoned", "")
        pytest.fail("PERSIST_FAULT_MARKER_MISSING")
    led.close()


def test_unsettled_reservation_and_unknown_billing_not_zeroed(tmp_path):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-c2",
        caps=_caps(), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L1", physical_id="UNSETT01",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.05)
    led.reserve(run_id="r", logical_id="L2", physical_id="UNSETT02",
                phase="opt", prompt_sha="s", res_in=5, res_out=5, res_cost=0.02)
    led.settle_unknown_and_block(physical_id="UNSETT01", reason="MISSING_USAGE")
    snap = led.snapshot()
    # the OTHER reservation must remain outstanding
    assert snap["outstanding_reserved_cost_usd"] == pytest.approx(0.02)
    assert snap["unknown_usage_count"] == 1
    assert snap["blocked"] is True
    # reopen
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    snap2 = rec2.snapshot_flat()
    assert snap2["blocked"] is True
    assert snap2["unknown_usage_count"] == 1
    assert snap2["outstanding_reserved_cost_usd"] == pytest.approx(0.02)
    led.close()


def test_concurrent_settle_and_reserve_after_block(tmp_path):
    import threading

    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-c3",
        caps=_caps(max_cost_usd=0.10, max_physical=100), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L1", physical_id="CONC0001",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.05)
    errors = []

    def settle_over():
        try:
            led.settle_actual(physical_id="CONC0001", actual_in=1, actual_out=1,
                              observed_cost=0.50, http_status=200,
                              model_returned="m", finish_reason="stop")
        except Exception as e:
            errors.append(f"settle:{type(e).__name__}")

    def reserve_new():
        try:
            led.reserve(run_id="r", logical_id="L2", physical_id="CONC0002",
                        phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
        except Exception as e:
            errors.append(f"reserve:{type(e).__name__}")

    threads = [threading.Thread(target=settle_over), threading.Thread(target=reserve_new)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    assert rec2._body["blocked"] is True
    led.close()


_WORKER = textwrap.dedent(
    """
    import sys
    sys.path.insert(0, sys.argv[1])
    from src.runtime.auth_ledger import AuthorizationRecord, AuthBudgetLedger
    rec = AuthorizationRecord.open_existing(sys.argv[2], secret_key=sys.argv[3])
    led = AuthBudgetLedger(sys.argv[4], rec)
    tag = sys.argv[5]
    try:
        led.reserve(run_id=tag, logical_id=f"L{tag}", physical_id=f"MP{tag}XXXX",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
        print("OK")
    except Exception as e:
        print("ERR", type(e).__name__)
    """
)


def test_multiprocess_restart_keeps_consumed(tmp_path):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-c4",
        caps=_caps(max_physical=10), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "w0.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="MPAAAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()
    n = rec.snapshot_flat()["physical_attempts"]
    # new process / new DB
    r = subprocess.run(
        [sys.executable, "-c", _WORKER, str(ROOT),
         str(tmp_path / "authorization_record.json"), SECRET,
         str(tmp_path / "w1.sqlite"), "W1"],
        capture_output=True, text=True, timeout=60,
    )
    assert "OK" in r.stdout
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    assert rec2.consumed["physical_attempts"] == n + 1
