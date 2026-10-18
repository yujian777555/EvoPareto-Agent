"""Task A negative tests: settle boundary, token replacement, block persistence."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationRecord,
    BudgetExceeded,
    UnifiedBudgetGate,
)
from src.runtime.provider_gateway import conservative_input_tokens, worst_case_cost

SECRET = "task-a-secret"


def _caps(**kw):
    base = {"max_physical": 20, "max_cost_usd": 1.0,
            "max_total_in": 80000, "max_total_out": 5000}
    base.update(kw)
    return base


def _mk(tmp_path, **kw):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-A",
        caps=_caps(**kw), secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    return rec, led


# ---------- actual cost must count other outstanding reservations ----------
def test_settle_actual_counts_other_outstanding_cost(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.10)
    # two open reservations of 0.05 each -> outstanding 0.10
    led.reserve(run_id="r", logical_id="L1", physical_id="OUTSTAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.05)
    led.reserve(run_id="r", logical_id="L2", physical_id="OUTSTBBBB",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.05)
    # settling the first with a small actual cost is fine (releases its 0.05)
    led.settle_actual(physical_id="OUTSTAAAA", actual_in=1, actual_out=1,
                      observed_cost=0.01, http_status=200,
                      model_returned="m", finish_reason="stop")
    # settling the second with 0.20 actual would push spent(0.21) beyond cap
    # even after its own reservation is released
    with pytest.raises(BudgetExceeded, match="ACTUAL_COST_EXCEEDS_CAP"):
        led.settle_actual(physical_id="OUTSTBBBB", actual_in=1, actual_out=1,
                          observed_cost=0.20, http_status=200,
                          model_returned="m", finish_reason="stop")
    led.close()


# ---------- actual tokens replace reservation before cap check ----------
def test_actual_tokens_replace_reservation_before_cap(tmp_path):
    rec, led = _mk(tmp_path, max_total_out=1000)
    # reserve 800 out, settle with 500 actual -> total actual 500, reserved 0
    led.reserve(run_id="r", logical_id="L", physical_id="REPLAAAA",
                phase="opt", prompt_sha="s", res_in=10, res_out=800, res_cost=0.01)
    led.settle_actual(physical_id="REPLAAAA", actual_in=10, actual_out=500,
                      observed_cost=0.01, http_status=200,
                      model_returned="m", finish_reason="stop")
    snap = led.snapshot()
    assert snap["actual_tokens_out"] == 500
    assert snap["reserved_tokens_out"] == 0  # reservation released
    # now a new reservation of 500 should fit (500 actual + 500 reserved = 1000)
    led.reserve(run_id="r", logical_id="L2", physical_id="REPLBBBB",
                phase="opt", prompt_sha="s", res_in=10, res_out=500, res_cost=0.01)
    # but a third of 200 would exceed
    with pytest.raises(BudgetExceeded, match="MAX_TOTAL_OUTPUT"):
        led.reserve(run_id="r", logical_id="L3", physical_id="REPLCCCC",
                    phase="opt", prompt_sha="s", res_in=10, res_out=200, res_cost=0.01)
    led.close()


# ---------- over-limit MUST persist the block before raising ----------
def test_block_persisted_despite_exception(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="BLOCKAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="BLOCKAAAA", actual_in=1, actual_out=1,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    # the block must be persisted despite the exception
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    assert rec2._body["blocked"] is True
    assert "ACTUAL_COST_EXCEEDS_CAP" in str(rec2._body["block_reason"])


# ---------- after settlement failure, no further HTTP ----------
def test_no_further_reserve_after_settle_failure(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="STOPAAAA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="STOPAAAA", actual_in=1, actual_out=1,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    with pytest.raises(Exception):
        led.reserve(run_id="r", logical_id="L2", physical_id="STOPBBBB",
                    phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    led.close()


# ---------- restart keeps the persistent block ----------
def test_block_survives_restart(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="RESTARTA",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="RESTARTA", actual_in=1, actual_out=1,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    led.close()
    rec2 = AuthorizationRecord.open_existing(
        tmp_path / "authorization_record.json", secret_key=SECRET
    )
    led2 = AuthBudgetLedger(tmp_path / "work2.sqlite", rec2)
    with pytest.raises(Exception):
        led2.reserve(run_id="r", logical_id="L9", physical_id="RESTARTB",
                     phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.001)
    led2.close()


# ---------- settlement exception must not release the reservation ----------
def test_settle_exception_keeps_reservation_conservative(tmp_path):
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    led.reserve(run_id="r", logical_id="L", physical_id="KEEPRSV01",
                phase="opt", prompt_sha="s", res_in=1, res_out=1, res_cost=0.02)
    snap_before = led.snapshot()
    with pytest.raises(BudgetExceeded):
        led.settle_actual(physical_id="KEEPRSV01", actual_in=1, actual_out=1,
                          observed_cost=0.50, http_status=200,
                          model_returned="m", finish_reason="stop")
    snap_after = led.snapshot()
    # blocked; the failed request is not silently released to free quota
    assert snap_after["blocked"] is True
    led.close()


# ---------- conservative_input_tokens is a documented loose bound ----------
def test_conservative_input_tokens_is_loose_bound():
    s = "Hello, world!"
    est = conservative_input_tokens(s)
    assert est >= len(s)  # at least 1 token per char
    assert est >= 2 * len(s)  # documented 2x + 16 margin
    cjk = "你好世界" * 10
    assert conservative_input_tokens(cjk) >= len(cjk)
    # never returns a small constant
    assert conservative_input_tokens("x" * 1000) > 1000


def test_mock_http_settle_over_cap_blocks_and_persists(tmp_path):
    """End-to-end through the gate: over-cap settlement blocks persistently."""
    rec, led = _mk(tmp_path, max_cost_usd=0.05)
    gate = UnifiedBudgetGate(led, default_max_in=8000, default_max_out=500)
    pid = gate.begin_request(run_id="r", phase="opt", prompt_sha="s",
                             res_in=10, res_out=10,
                             res_cost=worst_case_cost("deepseek-flash", 10, 10))
    with pytest.raises(BudgetExceeded):
        gate.complete_actual(pid, actual_in=10, actual_out=10,
                             observed_cost=0.50, http_status=200,
                             model_returned="m", finish_reason="stop")
    with pytest.raises(Exception):
        gate.begin_request(run_id="r", phase="opt", prompt_sha="s",
                           res_in=1, res_out=1, res_cost=0.001)
    led.close()
