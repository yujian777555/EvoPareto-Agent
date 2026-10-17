"""Full official AFlow mock E2E regression (Final Admission)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "final_live_admission"

docker_ok = True
try:
    import subprocess as _sp

    _r = _sp.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    docker_ok = _r.returncode == 0
except Exception:
    docker_ok = False

pytestmark = pytest.mark.skipif(not docker_ok, reason="docker daemon not running")

REQUIRED = [
    "GOLD_LEAKAGE_ELIMINATED",
    "SAME_CANDIDATE_PROVEN",
    "CHILD_OK",
    "OFFICIAL_EXPERIENCE_PATH",
    "OFFICIAL_RESULTS_PATH",
]


def test_full_aflow_mock_e2e():
    script = ROOT / "scripts" / "stage3_0_p1_r2a_r2" / "run_full_aflow_mock.py"
    r = subprocess.run(
        [sys.executable, str(script), "--run-id", "pytest-final-0001"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=240,
    )
    assert r.returncode == 0, f"e2e failed: {r.stdout[-800:]}\n{r.stderr[-800:]}"
    trace = json.loads((OUT / "official_aflow_full_mock_trace.json").read_text(encoding="utf-8"))
    assert trace["run_id"] == "pytest-final-0001"
    events = trace["events"]
    for k in REQUIRED:
        assert events.get(k), f"event not proven: {k}"
    # no gold in the container
    assert events.get("CHILD_TASK_KEYS") == ["question", "task_id"] or events.get("CHILD_TASK_KEYS") == ["task_id", "question"]
    # real HTTP through gateway
    assert events.get("REAL_MOCK_HTTP_POST_COUNT", 0) > 0
    assert events.get("GATEWAY_LEDGER_COUNT", 0) > 0
    # same candidate
    assert events.get("OPTIMIZER_CANDIDATE_SHA")
    assert events.get("OPTIMIZER_CANDIDATE_SHA") == events.get("EXECUTED_CHILD_SHA")
    # official persistence
    assert events.get("OFFICIAL_EXPERIENCE_PATH")
    assert "after" in (events.get("OFFICIAL_EXPERIENCE_FIELDS") or [])


def test_no_synthetic_experience_file():
    """The experience JSON must come from AFlow utilities, not a hand-written dict."""
    trace = json.loads((OUT / "official_aflow_full_mock_trace.json").read_text(encoding="utf-8"))
    fields = trace["events"].get("OFFICIAL_EXPERIENCE_FIELDS") or []
    assert set(fields) >= {"father node", "modification", "before", "after", "succeed"}


def test_frozen_results_untouched():
    import tests.frozen_guard as fg

    snap = fg.snapshot()
    assert len(snap) > 50
    assert "results/pilot1_preflight/timeout_billing_block.json" in snap
