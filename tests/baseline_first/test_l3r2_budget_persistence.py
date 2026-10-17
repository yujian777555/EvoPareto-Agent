"""Level 3-R2 adversarial budget tests (Task A/C/E). Offline only, no real API."""
from __future__ import annotations

import json
import shutil
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    STATE_RESERVED,
    STATE_SETTLED_ACTUAL,
    STATE_SETTLED_UNKNOWN_BLOCKED,
    AuthBudgetLedger,
    AuthorizationIntegrityError,
    AuthorizationMissing,
    AuthorizationRecord,
    BudgetExceeded,
    DuplicatePhysicalRequest,
    DuplicateSettlement,
    UnifiedBudgetGate,
    UnknownBillingBlocked,
)

SECRET = "test-secret-key-not-for-git"


def _caps():
    return {
        "max_physical": 10,
        "max_cost_usd": 1.00,
        "max_total_in": 80000,
        "max_total_out": 5000,
    }


@pytest.fixture()
def workdir(tmp_path):
    return tmp_path


def _make(tmp_path, *, record_name="authorization_record.json", db_name="work.sqlite"):
    rec_path = tmp_path / record_name
    rec = AuthorizationRecord.create(rec_path, auth_id="auth-A", caps=_caps(), secret_key=SECRET)
    led = AuthBudgetLedger(tmp_path / db_name, rec)
    return rec, led


# ---------------- Task A: persistence ----------------

def test_fresh_authorization_starts_at_zero(workdir):
    rec, led = _make(workdir)
    assert rec.consumed["physical_attempts"] == 0
    assert rec.remaining_physical() == 10
    led.close()


def test_create_twice_rejected(workdir):
    rec, led = _make(workdir)
    led.close()
    with pytest.raises(Exception, match="ALREADY_EXISTS"):
        AuthorizationRecord.create(
            workdir / "authorization_record.json", auth_id="auth-B",
            caps=_caps(), secret_key=SECRET,
        )


def test_consume_then_restart_keeps_quota(workdir):
    rec, led = _make(workdir)
    for i in range(2):
        led.reserve(run_id="r1", logical_id=f"L{i}", physical_id=f"PHYSA{i:04d}",
                    phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
        led.settle_actual(physical_id=f"PHYSA{i:04d}", actual_in=5, actual_out=5,
                          observed_cost=0.001, http_status=200,
                          model_returned="deepseek-flash", finish_reason="stop")
    assert rec.remaining_physical() == 8
    led.close()

    # "restart" = reopen the same record
    rec2 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    assert rec2.remaining_physical() == 8, "restart must not restore quota"
    assert rec2.consumed["physical_attempts"] == 2


def test_new_run_id_does_not_reset_quota(workdir):
    rec, led = _make(workdir)
    led.reserve(run_id="run-A", logical_id="L", physical_id="PHYSPAXXX",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.settle_actual(physical_id="PHYSPAXXX", actual_in=1, actual_out=1,
                      observed_cost=0.001, http_status=200,
                      model_returned="m", finish_reason="stop")
    # different run_id on the SAME authorization
    led.reserve(run_id="run-B", logical_id="L2", physical_id="PHYSPBXXX",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()
    rec2 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    assert rec2.consumed["physical_attempts"] == 2  # both runs counted


def test_db_delete_does_not_restore_quota(workdir):
    rec, led = _make(workdir)
    for i in range(2):
        led.reserve(run_id="r", logical_id=f"L{i}", physical_id=f"PHYSD{i:04d}",
                    phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
        led.settle_actual(physical_id=f"PHYSD{i:04d}", actual_in=5, actual_out=5,
                          observed_cost=0.001, http_status=200,
                          model_returned="m", finish_reason="stop")
    led.close()
    # delete the WORKING db
    (workdir / "work.sqlite").unlink()
    # reopen: record still holds consumption
    rec2 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    assert rec2.remaining_physical() == 8, "DB delete must not restore quota"
    led2 = AuthBudgetLedger(workdir / "work2.sqlite", rec2)
    # 9th request ok (remaining 8 -> after 1 more = 7)
    led2.reserve(run_id="r", logical_id="L9", physical_id="PHYSEXXXX",
                 phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led2.close()
    rec3 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    assert rec3.consumed["physical_attempts"] == 3


def test_db_path_change_does_not_restore_quota(workdir):
    rec, led = _make(workdir, db_name="db1.sqlite")
    led.reserve(run_id="r", logical_id="L", physical_id="PHYSP1XXXX",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.settle_actual(physical_id="PHYSP1XXXX", actual_in=1, actual_out=1,
                      observed_cost=0.001, http_status=200,
                      model_returned="m", finish_reason="stop")
    led.close()
    rec2 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    led2 = AuthBudgetLedger(workdir / "db2.sqlite", rec2)
    assert rec2.remaining_physical() == 9
    led2.close()


def test_missing_record_fail_closed(workdir):
    with pytest.raises(AuthorizationMissing):
        AuthorizationRecord.open_existing(workdir / "nope.json", secret_key=SECRET)


def test_corrupt_record_fail_closed(workdir):
    rec, led = _make(workdir)
    led.close()
    p = workdir / "authorization_record.json"
    body = json.loads(p.read_text(encoding="utf-8"))
    body["consumed"]["physical_attempts"] = 999  # try to inflate, then restore
    p.write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(AuthorizationIntegrityError):
        AuthorizationRecord.open_existing(p, secret_key=SECRET)


def test_delete_record_does_not_mint_new_quota(workdir):
    rec, led = _make(workdir)
    led.reserve(run_id="r", logical_id="L", physical_id="PHYSP1XXXX",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()
    (workdir / "authorization_record.json").unlink()
    with pytest.raises(AuthorizationMissing):
        AuthorizationRecord.open_existing(
            workdir / "authorization_record.json", secret_key=SECRET
        )


def test_historical_level3_requests_migrated_exactly(workdir):
    """Two live Level 3 requests must be inheritable once, not double-billed."""
    # seed the record as if migrated from live Level 3
    rec_path = workdir / "authorization_record.json"
    rec = AuthorizationRecord.create(
        rec_path, auth_id="auth-mig", caps=_caps(), secret_key=SECRET
    )
    # migrate 2 historical requests (as consumed actuals, no live sends)
    def _mut(body):
        body["consumed"]["physical_attempts"] = 2
        body["consumed"]["actual_tokens_in"] = 162
        body["consumed"]["actual_tokens_out"] = 454
        body["consumed"]["spent_cost_usd"] = 0.0005934
        body.setdefault("history_tail", []).append({"kind": "MIGRATED", "n": 2})
    rec.mutate(_mut)
    rec2 = AuthorizationRecord.open_existing(rec_path, secret_key=SECRET)
    assert rec2.consumed["physical_attempts"] == 2
    assert rec2.consumed["actual_tokens_in"] == 162
    assert rec2.consumed["actual_tokens_out"] == 454
    assert rec2.remaining_physical() == 8  # 10 - 2


# ---------------- Task C: state machine ----------------

def test_duplicate_physical_id_rejected(workdir):
    rec, led = _make(workdir)
    led.reserve(run_id="r", logical_id="L", physical_id="DUPID001",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    with pytest.raises(DuplicatePhysicalRequest):
        led.reserve(run_id="r", logical_id="L2", physical_id="DUPID001",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()


def test_double_settlement_rejected(workdir):
    rec, led = _make(workdir)
    led.reserve(run_id="r", logical_id="L", physical_id="SETTLE01",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.settle_actual(physical_id="SETTLE01", actual_in=1, actual_out=1,
                      observed_cost=0.001, http_status=200,
                      model_returned="m", finish_reason="stop")
    with pytest.raises(DuplicateSettlement):
        led.settle_actual(physical_id="SETTLE01", actual_in=1, actual_out=1,
                          observed_cost=0.001, http_status=200,
                          model_returned="m", finish_reason="stop")
    with pytest.raises(DuplicateSettlement):
        led.settle_unknown_and_block(physical_id="SETTLE01", reason="X")
    led.close()


def test_unknown_billing_blocks_persistently(workdir):
    rec, led = _make(workdir)
    led.reserve(run_id="r", logical_id="L", physical_id="UNKNWN01",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.05)
    led.settle_unknown_and_block(physical_id="UNKNWN01", reason="MISSING_USAGE")
    with pytest.raises(UnknownBillingBlocked):
        led.reserve(run_id="r", logical_id="L2", physical_id="UNKNWN02",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    # block survives reopen
    rec2 = AuthorizationRecord.open_existing(
        workdir / "authorization_record.json", secret_key=SECRET
    )
    assert rec2._body["blocked"] is True
    led.close()


def test_outstanding_reserved_cost_counts_toward_cap(workdir):
    """Two open reservations must not jointly exceed the cost cap."""
    caps = dict(_caps())
    caps["max_cost_usd"] = 0.05
    rec = AuthorizationRecord.create(
        workdir / "authorization_record.json", auth_id="auth-c",
        caps=caps, secret_key=SECRET,
    )
    led = AuthBudgetLedger(workdir / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L1", physical_id="OUTST001",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.03)
    # second reservation would make outstanding+new = 0.06 > 0.05
    with pytest.raises(BudgetExceeded, match="MAX_COST"):
        led.reserve(run_id="r", logical_id="L2", physical_id="OUTST002",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.03)
    led.close()


def test_physical_cap_after_mixed_settlements(workdir):
    caps = dict(_caps())
    caps["max_physical"] = 3
    rec = AuthorizationRecord.create(
        workdir / "authorization_record.json", auth_id="auth-p",
        caps=caps, secret_key=SECRET,
    )
    led = AuthBudgetLedger(workdir / "work.sqlite", rec)
    for i in range(3):
        pid = f"PHYCAP{i:02d}"
        led.reserve(run_id="r", logical_id=f"L{i}", physical_id=pid,
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
        led.settle_actual(physical_id=pid, actual_in=1, actual_out=1,
                          observed_cost=0.001, http_status=200,
                          model_returned="m", finish_reason="stop")
    with pytest.raises(BudgetExceeded, match="MAX_PHYSICAL"):
        led.reserve(run_id="r", logical_id="L9", physical_id="PHYCAP99",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.01)
    led.close()


def test_total_output_token_cap(workdir):
    caps = dict(_caps())
    caps["max_total_out"] = 100
    rec = AuthorizationRecord.create(
        workdir / "authorization_record.json", auth_id="auth-t",
        caps=caps, secret_key=SECRET,
    )
    led = AuthBudgetLedger(workdir / "work.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="TOKOUT01",
                phase="opt", prompt_sha="s", res_in=1, res_out=80, res_cost=0.01)
    with pytest.raises(BudgetExceeded, match="MAX_TOTAL_OUTPUT"):
        led.reserve(run_id="r", logical_id="L2", physical_id="TOKOUT02",
                    phase="opt", prompt_sha="s", res_in=1, res_out=50, res_cost=0.01)
    led.close()


def test_concurrent_reservations_never_exceed_cost_cap(workdir):
    caps = dict(_caps())
    caps["max_cost_usd"] = 0.10
    caps["max_physical"] = 100
    rec = AuthorizationRecord.create(
        workdir / "authorization_record.json", auth_id="auth-cc",
        caps=caps, secret_key=SECRET,
    )
    led = AuthBudgetLedger(workdir / "work.sqlite", rec)
    errors = []

    def worker(n):
        for i in range(10):
            try:
                led.reserve(run_id="r", logical_id=f"{n}-{i}",
                            physical_id=f"CC{n:02d}{i:02d}xx",
                            phase="opt", prompt_sha="s",
                            res_in=1, res_out=1, res_cost=0.02)
            except Exception as e:
                errors.append(type(e).__name__)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = led.snapshot()
    consumed = snap["consumed"]
    total_committed = float(consumed["spent_cost_usd"]) + float(consumed["outstanding_reserved_cost_usd"])
    assert total_committed <= 0.10 + 1e-9
    assert "BudgetExceeded" in errors
    led.close()


# ---------------- Task B: unified gate ----------------

def test_unified_gate_covers_optimizer_and_child(workdir):
    rec, led = _make(workdir)
    gate = UnifiedBudgetGate(led, default_max_in=8000, default_max_out=500)
    p1 = gate.begin_request(run_id="r", phase="optimizer", prompt_sha="a",
                            res_in=100, res_out=50, res_cost=0.01)
    p2 = gate.begin_request(run_id="r", phase="workflow_execution", prompt_sha="b",
                            res_in=100, res_out=50, res_cost=0.01)
    gate.complete_actual(p1, actual_in=10, actual_out=5, observed_cost=0.001,
                         http_status=200, model_returned="m", finish_reason="stop")
    gate.complete_actual(p2, actual_in=12, actual_out=6, observed_cost=0.001,
                         http_status=200, model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    assert snap["consumed"]["physical_attempts"] == 2
    phases = [r["request_phase"] for r in led.request_rows()]
    assert "optimizer" in phases and "workflow_execution" in phases
    led.close()


def test_graph_prompt_invalid_means_zero_real_requests(workdir):
    """Invalid bundle must fail BEFORE any budget reservation."""
    from src.runtime.candidate_bundle import BundleValidationError, build_bundle

    rec, led = _make(workdir)
    gate = UnifiedBudgetGate(led, default_max_in=8000, default_max_out=500)
    with pytest.raises(BundleValidationError):
        build_bundle(graph_src="def broken(:\n", prompt_field="x")
    # no reservation happened
    assert led.snapshot()["consumed"]["physical_attempts"] == 0
    led.close()
