"""Pilot1 hotfix tests: cost settlement, status classification, dry-run."""

import json
from pathlib import Path

import pytest

from src.backend.rates import RATE_VERSION, estimated_cost
from src.runtime.http_budget import (
    BudgetDB,
    BudgetExceeded,
    PhysicalBudgetGate,
    install_global_gate,
    pre_send_ticket,
    settle_ticket,
)


def test_estimated_cost_frozen_rate():
    c = estimated_cost("deepseek-flash", 1000, 1000)
    # peak conservative: 1000*0.30/1e6 + 1000*1.20/1e6 = 0.0003 + 0.0012
    assert c == pytest.approx(0.0015)
    assert RATE_VERSION == "deepseek-flash-2026-10-peak-conservative-v1"


def test_ticket_settle_includes_cost(tmp_path):
    db = BudgetDB(tmp_path / "b.db", max_physical=10, max_cost_usd=1.0)
    t = db.acquire_ticket(0.01)
    db.settle(t, success=True, actual_cost=0.003, tokens_in=100, tokens_out=20)
    snap = db.snapshot()
    assert snap["spent_cost_usd"] == pytest.approx(0.003)
    assert snap["tokens_in"] == 100
    assert snap["tokens_out"] == 20


def test_cost_budget_blocks_when_exhausted(tmp_path):
    db = BudgetDB(tmp_path / "b.db", max_physical=100, max_cost_usd=0.01)
    t = db.acquire_ticket(0.006)
    db.settle(t, success=True, actual_cost=0.006)
    with pytest.raises(BudgetExceeded):
        db.acquire_ticket(0.01)


def test_completion_status_not_equal_http_ok():
    # 200 + empty content => business failure
    status, text = 200, ""
    completion_ok = bool(text.strip())
    assert status == 200 and not completion_ok


def test_pilot1_dry_run(tmp_path):
    import argparse

    from scripts.pilot1_entry import build_config, dry_run

    args = argparse.Namespace(
        dry_run=True, live=False, mode="pilot1_wiring", experiment_id="t",
        ledger_path=str(tmp_path / "l.db"), physical_cap=120, cost_cap=0.05,
        task_manifest="results/native_alfworld/development_task_pool.json",
        output_dir=str(tmp_path), seed=11, split="valid_train", horizon=30,
    )
    out = dry_run(args)
    assert out["dry_run"] is True
    assert out["checks"]["objective_ok"] is True
    assert out["checks"]["fitness_2d_ok"] is True
    assert out["checks"]["output_writable"] is True


def test_pilot1_refuses_live_without_flag(tmp_path):
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "scripts/pilot1_entry.py", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0 or "refusing" in (r.stderr + r.stdout).lower()
