"""Pilot1 final admission tests: cost fail-closed + reconciliation."""

import json
from pathlib import Path

import pytest

from src.backend.cost_status import (
    KNOWN,
    UNKNOWN_RATE,
    UNKNOWN_USAGE,
    backend_estimated_cost,
    estimate_cost,
)


def test_cost_known_when_usage_and_rate():
    c = estimate_cost("deepseek-flash", 1000, 500)
    assert c.status == KNOWN
    # peak conservative: 1000*0.30/1e6 + 500*1.20/1e6 = 0.0003 + 0.0006
    assert c.cost == pytest.approx(0.0009)


def test_cost_unknown_usage_not_zero_pass():
    c = estimate_cost("deepseek-flash", None, 5)
    assert c.status == UNKNOWN_USAGE
    assert c.is_known is False


def test_cost_unknown_model_not_silent():
    c = estimate_cost("gpt-99", 10, 10)
    assert c.status == UNKNOWN_RATE
    assert c.is_known is False


def test_backend_and_transport_same_formula():
    assert backend_estimated_cost("deepseek-flash", 2000, 1000) == pytest.approx(
        estimate_cost("deepseek-flash", 2000, 1000).cost
    )


def test_native_smoke_record_exists():
    p = Path("results/pilot1_final_offline/native_smoke.json")
    assert p.exists(), "docker native smoke must be recorded"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["native_dry_run_status"] == "PASS"
    assert d["checks"]["native_reset_pass"] is True
    assert d["checks"]["native_step_pass"] is True
    assert "valid_train" in d.get("actual_game_id", "")
    assert d["episode"]["evaluation_kind"] == "real_environment"


def test_manifest_sha_recorded():
    d = json.loads(Path("results/pilot1_final_offline/native_smoke.json").read_text(encoding="utf-8"))
    assert d.get("manifest_sha256")


def test_pilot1_entry_still_refuses_live_by_default(tmp_path):
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "scripts/pilot1_entry.py", "--output-dir", str(tmp_path)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0 or "refusing" in (r.stderr + r.stdout).lower()
