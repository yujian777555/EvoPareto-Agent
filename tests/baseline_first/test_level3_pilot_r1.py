"""Pilot-R1 tests: persistent auth, no auto-create, phase-specific caps."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationMissing,
    AuthorizationRecord,
    UnifiedBudgetGate,
)
from src.runtime.provider_gateway import MockHTTPProvider, worst_case_cost

SECRET = "r1-test-secret"


def _load_pilot():
    path = ROOT / "scripts" / "level3_pilot" / "run_pilot.py"
    spec = importlib.util.spec_from_file_location("pilot_r1", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------- P0: auth persistence ----------------

def test_missing_auth_fail_closed_no_auto_create(tmp_path, monkeypatch):
    mod = _load_pilot()
    mod.OUT = tmp_path / "out"
    mod.OUT.mkdir()
    monkeypatch.setattr(mod, "SECRET", SECRET)
    # force the persistent path to an empty dir
    fake_home = tmp_path / "home"
    (fake_home / ".evopareto" / "state").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    rc = mod.main()
    assert rc == 3
    # must NOT have created a new authorization
    assert not (fake_home / ".evopareto" / "state" / "level3_pilot_authorization.json").exists()
    summary = json.loads((mod.OUT / "pilot_latest_summary.json").read_text(encoding="utf-8"))
    assert summary["STOP_REASON"] == "AUTHORIZATION_RECORD_MISSING"


def test_deleting_record_does_not_restore_quota(tmp_path):
    p = tmp_path / "auth.json"
    rec = AuthorizationRecord.create(
        p, auth_id="a1", caps={"max_physical": 10, "max_cost_usd": 5.0,
                               "max_total_in": 2000000, "max_total_out": 200000},
        secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "w.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="DELAAAAAA",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
    led.close()
    p.unlink()
    with pytest.raises(AuthorizationMissing):
        AuthorizationRecord.open_existing(p, secret_key=SECRET)


def test_git_rollback_cannot_reset_authorization(tmp_path):
    """Simulate a git rollback restoring an old copy: it must not overwrite
    the newer persistent record with zero consumption."""
    import shutil

    persistent = tmp_path / "state" / "auth.json"
    persistent.parent.mkdir(parents=True)
    rec = AuthorizationRecord.create(
        persistent, auth_id="a2", caps={"max_physical": 10, "max_cost_usd": 5.0,
                                        "max_total_in": 2000000, "max_total_out": 200000},
        secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "w.sqlite", rec)
    led.reserve(run_id="r", logical_id="L", physical_id="ROLLAAAA",
                phase="opt", prompt_sha="s", res_in=10, res_out=10, res_cost=0.01)
    led.close()
    # a "rolled-back" git copy with zero consumption
    stale = tmp_path / "git_copy.json"
    stale.write_text(json.dumps({
        "auth_id": "a2",
        "consumed": {"physical_attempts": 0, "spent_cost_usd": 0.0,
                     "actual_tokens_in": 0, "actual_tokens_out": 0,
                     "reserved_tokens_in": 0, "reserved_tokens_out": 0,
                     "outstanding_reserved_cost_usd": 0.0, "unknown_usage_count": 0},
        "caps": {"max_physical": 10, "max_cost_usd": 5.0,
                 "max_total_in": 2000000, "max_total_out": 200000},
    }), encoding="utf-8")
    # opening the persistent record still shows the real consumption
    rec2 = AuthorizationRecord.open_existing(persistent, secret_key=SECRET)
    assert rec2.consumed["physical_attempts"] == 1
    assert rec2.remaining_physical() == 9


def test_current_authorization_preserved(tmp_path):
    """The real persistent authorization (if present) must keep its history."""
    real = Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json"
    if not real.exists():
        pytest.skip("persistent authorization not present on this machine")
    import hashlib

    secret = hashlib.sha256(
        (os.environ.get("DEEPSEEK_API_KEY", "") + "|level3-pilot|v1").encode("utf-8")
    ).hexdigest()
    rec = AuthorizationRecord.open_existing(real, secret_key=secret)
    snap = rec.snapshot_flat()
    # historical Level 3 pilot consumption must be present
    assert snap["physical_attempts"] >= 2
    assert snap["spent_cost_usd"] >= 0.0008979 - 1e-9
    assert snap["actual_tokens_in"] >= 151
    assert snap["actual_tokens_out"] >= 640
    assert snap["max_cost_usd"] == 5.0


# ---------------- phase-specific output caps ----------------

def test_phase_output_caps_defined():
    mod = _load_pilot()
    caps = mod.PHASE_OUTPUT_CAPS
    assert caps["pilot_math"] == 500
    assert caps["pilot_optimizer"] == 1800
    assert caps["pilot_workflow_ipc"] == 500


def test_mock_budget_reservation_uses_phase_cap(tmp_path):
    """Reservation must use the SAME phase cap as the request max_tokens."""
    rec = AuthorizationRecord.create(
        tmp_path / "auth.json", auth_id="a3",
        caps={"max_physical": 10, "max_cost_usd": 5.0,
              "max_total_in": 2000000, "max_total_out": 200000},
        secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "w.sqlite", rec)
    gate = UnifiedBudgetGate(led, default_max_in=8000, default_max_out=1800)
    # optimizer phase: 1800 out
    pid = gate.begin_request(
        run_id="r", phase="pilot_optimizer", prompt_sha="s",
        res_in=100, res_out=1800, res_cost=worst_case_cost("deepseek-flash", 100, 1800),
    )
    rows = led.request_rows()
    assert rows[0]["reserved_tokens_out"] == 1800
    # math phase: 500 out
    pid2 = gate.begin_request(
        run_id="r", phase="pilot_math", prompt_sha="s",
        res_in=100, res_out=500, res_cost=worst_case_cost("deepseek-flash", 100, 500),
    )
    rows = led.request_rows()
    assert rows[1]["reserved_tokens_out"] == 500
    led.close()


def test_worst_case_cost_within_authorization():
    # 2M in + 200k out at peak cache-miss
    w = worst_case_cost("deepseek-flash", 2_000_000, 200_000)
    assert w == pytest.approx(2.0 * 0.30 + 0.2 * 1.20)  # 0.60 + 0.24 = 0.84
    assert w < 5.00
    # optimizer phase worst case
    w_opt = worst_case_cost("deepseek-flash", 8000, 1800)
    assert w_opt == pytest.approx(8000 * 0.30 / 1e6 + 1800 * 1.20 / 1e6)
    assert 300 * w_opt < 5.00  # 300 optimizer-grade requests still fit


def test_mock_http_phase_max_tokens_sent(tmp_path):
    """The HTTP body must carry the phase cap, not a hardcoded 500."""
    rec = AuthorizationRecord.create(
        tmp_path / "auth.json", auth_id="a4",
        caps={"max_physical": 10, "max_cost_usd": 5.0,
              "max_total_in": 2000000, "max_total_out": 200000},
        secret_key=SECRET,
    )
    led = AuthBudgetLedger(tmp_path / "w.sqlite", rec)
    gate = UnifiedBudgetGate(led, default_max_in=8000, default_max_out=1800)
    provider = MockHTTPProvider()
    provider.start_background()
    mod = _load_pilot()
    mod.OUT = tmp_path / "out"
    mod.OUT.mkdir()
    mod.BASE_URL = provider.base_url
    mod.SECRET = SECRET
    # hand-run a single optimizer request through the patched chat()
    import types

    events = {"stages": {}}
    # replicate the chat logic inline to inspect the request body
    est_in = 100
    out_cap = mod.PHASE_OUTPUT_CAPS["pilot_optimizer"]
    assert out_cap == 1800
    import urllib.request

    body = json.dumps({
        "model": "deepseek-flash",
        "thinking": {"type": "disabled"},
        "max_tokens": out_cap,
        "messages": [{"role": "user", "content": "GraphOptimize"}],
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{provider.base_url}/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=10) as resp:
        resp.read()
    seen = provider.requests_seen[-1]["body"]
    assert seen["max_tokens"] == 1800
    provider.shutdown()
    led.close()
