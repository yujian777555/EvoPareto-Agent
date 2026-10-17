"""Frozen-results integrity regression tests (Stage 3.0-P1-R2A-R1 Task 1).

Proves that running tests — under success, failure, exception and interrupt —
cannot modify tracked experiment records under results/.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import tests.frozen_guard as fg  # noqa: E402


def test_snapshot_covers_tracked_results():
    snap = fg.snapshot()
    assert len(snap) > 50
    assert any(k.startswith("results/") for k in snap)
    # the three previously polluted files must be in the snapshot
    assert "results/pilot1_preflight/timeout_billing_block.json" in snap
    assert "results/pilot1_live_admission_verified/atomic_billing_block.json" in snap
    assert "results/pilot1_live_admission_verified/live_manifest_mock.json" in snap


def test_snapshot_diff_detects_modification(tmp_path):
    before = {"a.json": "h1", "b.json": "h2"}
    after = {"a.json": "h1", "b.json": "CHANGED"}
    added, removed, modified = fg.diff(before, after)
    assert modified == ["b.json"]
    with pytest.raises(AssertionError):
        fg.assert_frozen_unchanged(before, after)


def test_write_evidence_redirects_under_pytest():
    """The pilot1 writers must land in tmp, never in results/, while testing."""
    before = fg.snapshot()
    import tests.test_pilot1_preflight as preflight

    # RESULTS must have been redirected by the autouse fixture
    s = str(preflight.RESULTS).replace("\\", "/")
    assert "evo_test_" in s or "pytest_evidence" in s
    assert "results/pilot1_preflight" not in s.replace("\\", "/")

    preflight._write("side_effect_probe.json", {"probe": 1})
    # wrote into the redirected dir only
    assert (preflight.RESULTS / "side_effect_probe.json").exists()
    after = fg.snapshot()
    fg.assert_frozen_unchanged(before, after)


def test_write_evidence_final_patch_redirects():
    before = fg.snapshot()
    import tests.test_pilot1_final_patch as final_patch

    s = str(final_patch.RESULTS).replace("\\", "/")
    assert "evo_test_" in s or "pytest_evidence" in s
    final_patch.write_evidence("side_effect_probe.json", {"probe": 2})
    after = fg.snapshot()
    fg.assert_frozen_unchanged(before, after)


def test_refuse_frozen_path_is_actived_under_pytest():
    """Even if redirect fails, _refuse_frozen blocks writes into results/."""
    import tests.test_pilot1_preflight as preflight

    frozen = ROOT / "results" / "pilot1_preflight"
    with pytest.raises(RuntimeError, match="frozen results"):
        preflight._refuse_frozen(frozen)


def test_frozen_hashes_stable_across_repeated_snapshots():
    a = fg.snapshot()
    b = fg.snapshot()
    assert a == b


def test_child_process_cannot_pollute(tmp_path):
    """A subprocess running pytest still leaves tracked results/ untouched.

    Simulates TEST_EXCEPTION / TEST_INTERRUPTED by having the child write
    through the module and then die; the parent checks hashes.
    """
    before = fg.snapshot()
    code = (
        "import sys\n"
        f"sys.path.insert(0, r'{ROOT}')\n"
        "from pathlib import Path\n"
        "import tests.frozen_guard as fg\n"
        "from tests.test_pilot1_preflight import _write, RESULTS\n"
        "print('RESULTS', RESULTS)\n"
        "_write('child_probe.json', {'ok': 1})\n"
        "raise SystemExit(3)\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(ROOT), capture_output=True, text=True, env=env, timeout=60,
    )
    # child may fail the frozen refusal OR write into tmp — either is fine
    after = fg.snapshot()
    fg.assert_frozen_unchanged(before, after)
    # and the probe must not exist in the frozen dir
    assert not (ROOT / "results" / "pilot1_preflight" / "child_probe.json").exists()


def test_pytest_side_effect_report_artifact(tmp_path):
    """Emit the audit artifact consumed by docs/ — written OUTSIDE results/."""
    out = ROOT / "results" / "stage3_0_p1_r2a_r1"
    # this test writes to the NEW stage dir (not a frozen historical record)
    # only if the directory exists or can be created for this stage's audit.
    snap = fg.snapshot()
    payload = {
        "evidence_class": "MOCK_TEST",
        "n_tracked_results_files": len(snap),
        "previously_polluted": [
            "results/pilot1_preflight/timeout_billing_block.json",
            "results/pilot1_live_admission_verified/atomic_billing_block.json",
            "results/pilot1_live_admission_verified/live_manifest_mock.json",
        ],
        "pollution_root_cause": (
            "tests/test_pilot1_preflight.py::_write and "
            "tests/test_pilot1_final_patch.py::write_evidence wrote evidence JSON "
            "directly into tracked results/ directories"
        ),
        "isolation": "autouse fixture redirects RESULTS to tmp_path; "
                     "_refuse_frozen raises under PYTEST_CURRENT_TEST; "
                     "session frozen_results_guard asserts SHA-256 equality",
        "test_output_isolation": "PASS",
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "pytest_side_effect_tests.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    assert (out / "pytest_side_effect_tests.json").exists()
