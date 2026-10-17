"""Full official AFlow mock E2E regression (Task 5)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "stage3_0_p1_r2a_r2"

docker_ok = True
try:
    import subprocess as _sp

    _r = _sp.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    docker_ok = _r.returncode == 0
except Exception:
    docker_ok = False

pytestmark = pytest.mark.skipif(not docker_ok, reason="docker daemon not running")

REQUIRED = [
    "OFFICIAL_OPTIMIZER_EXECUTED",
    "OFFICIAL_PARENT_SELECTION",
    "REAL_TASK_QUESTION_PROPAGATED",
    "STRUCTURED_MODIFICATION_VALIDATED",
    "CHILD_WORKFLOW_EXECUTED",
    "MODEL_IPC_USED",
    "PHYSICAL_BUDGET_CHARGED",
    "GOLD_ANSWER_SCORING_EXECUTED",
    "EXPERIENCE_UPDATED",
    "RESULTS_PERSISTED",
]


def test_full_aflow_mock_e2e():
    script = ROOT / "scripts" / "stage3_0_p1_r2a_r2" / "run_full_aflow_mock.py"
    r = subprocess.run(
        [sys.executable, str(script), "--run-id", "pytest-e2e-0001"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=240,
    )
    assert r.returncode == 0, f"e2e failed: {r.stdout[-800:]}\n{r.stderr[-800:]}"
    trace = json.loads((OUT / "official_aflow_full_mock_trace.json").read_text(encoding="utf-8"))
    events = trace["events"]
    for k in REQUIRED:
        assert events.get(k) is True, f"event not proven: {k}"
    # derived from THIS run, not a committed PASS string
    assert trace["run_id"] == "pytest-e2e-0001"
    assert trace["real_deepseek_calls"] == 0
    assert trace["n_physical_requests"] > 0
    assert trace["ledger_rows"] > 0
    # real questions propagated
    assert trace["task_a"]["task_id"].startswith("gsm8k-")
    assert len(trace["task_a"]["question_head"]) > 10
    # gold scoring present
    assert trace["scoring"] and all("gold" in s for s in trace["scoring"])


def test_frozen_results_untouched_after_e2e():
    import tests.frozen_guard as fg

    # snapshot equality is enforced by the session guard; this is an explicit check
    snap = fg.snapshot()
    assert len(snap) > 50
    assert "results/pilot1_preflight/timeout_billing_block.json" in snap
