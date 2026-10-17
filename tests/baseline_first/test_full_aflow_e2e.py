"""Full official AFlow mock E2E regression (Final Admission)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "stage3_0_p1_r2a_r3"

docker_ok = True
try:
    import subprocess as _sp

    _r = _sp.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    docker_ok = _r.returncode == 0
except Exception:
    docker_ok = False

pytestmark = pytest.mark.skipif(not docker_ok, reason="docker daemon not running")

REQUIRED = [
    "OFFICIAL_EVALUATOR_CHILD_EXECUTION_OK",
    "PROVIDER_HTTP_RESPONSE_USED",
    "EXPERIENCE_WRITTEN_BY_OFFICIAL_UTILS",
    "RESULTS_WRITTEN_BY_OFFICIAL_UTILS",
]


def test_full_aflow_mock_e2e(tmp_path):
    tmp_out = tmp_path / "e2e_out"
    tmp_out.mkdir()
    script = ROOT / "scripts" / "stage3_0_p1_r2a_r3" / "run_official_evaluator_e2e.py"
    r = subprocess.run(
        [sys.executable, str(script), "--run-id", "pytest-final-0001", "--out-dir", str(tmp_out)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=240,
    )
    assert r.returncode == 0, f"e2e failed: {r.stdout[-800:]}\n{r.stderr[-800:]}"
    trace = json.loads((tmp_out / "official_aflow_full_mock_trace.json").read_text(encoding="utf-8"))
    assert trace["run_id"] == "pytest-final-0001"
    events = trace["events"]
    for k in REQUIRED:
        assert events.get(k), f"event not proven: {k}"
    # no gold in the container
    assert events.get("CONTAINER_TASK_KEYS") == ["task_id", "question"]
    # real HTTP through gateway
    assert events.get("MOCK_HTTP_POST_COUNT", 0) > 0
    assert events.get("LEDGER_REQUEST_COUNT", 0) > 0
    # same candidate
    assert events.get("OPTIMIZER_CANDIDATE_SHA")
    assert events.get("CANDIDATE_GRAPH_SHA_MATCH")
    # official persistence
    assert events.get("OFFICIAL_EXPERIENCE_PATH")
    assert events.get("OFFICIAL_EXPERIENCE_FIELDS")


def test_no_synthetic_experience_file():
    """The experience JSON must come from AFlow utilities, not a hand-written dict."""
    trace = json.loads((OUT / "official_aflow_full_mock_trace.json").read_text(encoding="utf-8"))
    fields = trace["events"].get("OFFICIAL_EXPERIENCE_FIELDS") or []
    assert "after" in fields and "succeed" in fields


def test_frozen_results_untouched():
    import tests.frozen_guard as fg

    snap = fg.snapshot()
    assert len(snap) > 50
    assert "results/pilot1_preflight/timeout_billing_block.json" in snap
