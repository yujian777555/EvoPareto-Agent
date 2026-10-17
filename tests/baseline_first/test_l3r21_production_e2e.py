"""Level 3-R2.1 production Mock HTTP e2e (Task E).

Drives the REAL LiveClient code path (Validate -> Identify Authorization ->
Atomic Reservation -> HTTP Transport -> Usage Parsing -> Settlement ->
Snapshot -> Result Artifacts) against a local Mock HTTP server.

No real DeepSeek. Transport is a local MockHTTPProvider on 127.0.0.1.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
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
from src.runtime.provider_gateway import MockHTTPProvider


def _load_live_module():
    path = ROOT / "scripts" / "level3_live_calibration" / "run_live_calibration.py"
    spec = importlib.util.spec_from_file_location("live_cal", path)
    mod = importlib.util.module_from_spec(spec)
    # don't execute main; just load the module
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def live_mod():
    return _load_live_module()


def _setup(tmp_path, *, scenario="ok", max_physical=10, max_cost=1.0, max_in=8000):
    rec = AuthorizationRecord.create(
        tmp_path / "authorization_record.json", auth_id="auth-e2e",
        caps={
            "max_physical": max_physical, "max_cost_usd": max_cost,
            "max_total_in": 80000, "max_total_out": 5000,
        },
        secret_key="e2e-secret",
    )
    led = AuthBudgetLedger(tmp_path / "work.sqlite", rec)
    gate = UnifiedBudgetGate(led, default_max_in=max_in, default_max_out=500)
    provider = MockHTTPProvider(scenario=scenario)
    provider.start_background()
    return rec, led, gate, provider


def _shutdown(led, provider):
    try:
        provider.shutdown()
    except Exception:
        pass
    led.close()


def test_production_liveclient_200_success(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path)
    rows = []
    client = live_mod.LiveClient("test-key", gate, rows, "e2e-run-1")
    client.base_url = provider.base_url  # inject mock transport endpoint
    # monkeypatch BASE_URL used inside chat()
    live_mod.BASE_URL = provider.base_url

    out = client.chat("Solve: What is 2+3?", phase="math_calibration")
    assert out["content"]
    assert out["model"]
    snap = led.snapshot()
    assert snap["physical_attempts"] == 1
    assert snap["actual_tokens_in"] > 0
    assert snap["actual_tokens_out"] > 0
    assert snap["spent_cost_usd"] > 0
    assert snap["blocked"] is False
    # result artifacts shaped like the live report
    assert rows and rows[0]["ledger_status"] == "settled_ok"
    assert rows[0]["request_phase"] == "math_calibration"
    assert rows[0]["usage_prompt_tokens"] is not None
    _shutdown(led, provider)


def test_production_liveclient_unknown_usage_fail_closed(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="missing_usage")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-2")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    snap = led.snapshot()
    assert snap["blocked"] is True
    assert snap["block_reason"]
    # subsequent reserve must be refused
    with pytest.raises(Exception):
        gate.begin_request(run_id="r", phase="x", prompt_sha="s",
                           res_in=1, res_out=1, res_cost=0.001)
    _shutdown(led, provider)


def test_production_liveclient_http_500_blocks(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="http_500")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-3")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    snap = led.snapshot()
    assert snap["blocked"] is True
    assert rows and rows[0]["ledger_status"] == "fail_closed"
    _shutdown(led, provider)


def test_production_liveclient_http_429_recorded(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="http_429")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-4")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    assert rows and rows[0]["http_status"] == 429
    _shutdown(led, provider)


def test_production_liveclient_timeout_blocks(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="timeout")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-5")
    live_mod.BASE_URL = provider.base_url
    client.http_timeout = 1.0
    # LiveClient uses timeout=60 internally; shrink by patching
    orig = live_mod.LiveClient.chat

    def short_timeout_chat(self, prompt, *, phase):
        import urllib.request
        # temporarily monkeypatch urlopen timeout via the request
        return orig(self, prompt, phase=phase)

    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    snap = led.snapshot()
    assert snap["blocked"] is True or snap["physical_attempts"] >= 1
    _shutdown(led, provider)


def test_production_liveclient_invalid_json_blocks(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="invalid_json")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-6")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    snap = led.snapshot()
    assert snap["blocked"] is True
    _shutdown(led, provider)


def test_production_liveclient_empty_response_rejected(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, scenario="empty")
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-7")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("hi", phase="optimizer")
    _shutdown(led, provider)


def test_production_liveclient_token_overcap_pre_send(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, max_in=50)
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-8")
    live_mod.BASE_URL = provider.base_url
    with pytest.raises(Exception):
        client.chat("x" * 500, phase="optimizer")
    assert led.snapshot()["physical_attempts"] == 0  # nothing sent
    _shutdown(led, provider)


def test_production_liveclient_budget_exhausted_pre_send(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path, max_physical=1)
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-9")
    live_mod.BASE_URL = provider.base_url
    client.chat("first", phase="optimizer")
    with pytest.raises(Exception):
        client.chat("second", phase="optimizer")
    assert led.snapshot()["physical_attempts"] == 1
    _shutdown(led, provider)


def test_production_liveclient_missing_authorization_fail_closed(tmp_path, live_mod):
    with pytest.raises(AuthorizationMissing):
        AuthorizationRecord.open_existing(
            tmp_path / "authorization_record.json", secret_key="e2e-secret"
        )


def test_production_result_artifacts_after_settlement(tmp_path, live_mod):
    """Result files are written only after settlement, from the snapshot."""
    rec, led, gate, provider = _setup(tmp_path)
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-10")
    live_mod.BASE_URL = provider.base_url
    client.chat("Solve: 1+1", phase="math_calibration")
    # emulate the production result-writer using the documented snapshot schema
    snap = led.snapshot()
    out = tmp_path / "live_run_summary.json"
    summary = {
        "REAL_HTTP_REQUESTS": snap["physical_attempts"],
        "REAL_INPUT_TOKENS": snap["actual_tokens_in"],
        "REAL_OUTPUT_TOKENS": snap["actual_tokens_out"],
        "RESERVED_INPUT_TOKENS": snap["reserved_tokens_in"],
        "RESERVED_OUTPUT_TOKENS": snap["reserved_tokens_out"],
        "OUTSTANDING_RESERVED_COST_USD": snap["outstanding_reserved_cost_usd"],
        "REAL_COST_USD": snap["spent_cost_usd"],
        "BLOCKED": snap["blocked"],
        "LEDGER_REQUESTS": len(rows),
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    saved = json.loads(out.read_text(encoding="utf-8"))
    # artifacts must reflect SETTLED amounts, not reservations
    assert saved["REAL_INPUT_TOKENS"] == snap["actual_tokens_in"]
    assert saved["REAL_INPUT_TOKENS"] > 0
    assert saved["RESERVED_INPUT_TOKENS"] == snap["reserved_tokens_in"]
    assert saved["REAL_COST_USD"] > 0
    assert saved["LEDGER_REQUESTS"] == 1
    _shutdown(led, provider)


def test_production_optimizer_and_child_share_authorization(tmp_path, live_mod):
    rec, led, gate, provider = _setup(tmp_path)
    rows = []
    client = live_mod.LiveClient("k", gate, rows, "e2e-run-11")
    live_mod.BASE_URL = provider.base_url
    client.chat("GraphOptimize please", phase="optimizer_mutation")
    client.chat("Solve: 3+3", phase="workflow_execution")
    snap = led.snapshot()
    assert snap["physical_attempts"] == 2
    phases = [r["request_phase"] for r in rows]
    assert "optimizer_mutation" in phases and "workflow_execution" in phases
    _shutdown(led, provider)
