"""Task B: hash gate regression tests + Task C: provenance audit tests."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

EXPECTED = "ddf055537d4618c86d736d4f0ed98fd4b23efec21f9e0ffe65a2c8ee022a6219"
RES3 = ROOT / "results" / "level3_pilot_r3"
SCRIPT = ROOT / "scripts" / "level3_pilot_r3" / "run_paired_35.py"

# load the pure function
import importlib.util

spec = importlib.util.spec_from_file_location("rp", SCRIPT)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
verify_taskset = rp.verify_taskset


def _load_tasks():
    conf = json.loads((RES3 / "paired_confirmation_set_35.json").read_text(encoding="utf-8"))
    return conf["tasks"], conf.get("task_set_sha256")


def _clone(tasks):
    return [dict(t) for t in tasks]


# ---- Task B: hash gate regression ----

def test_valid_frozen_taskset_passes():
    tasks, declared = _load_tasks()
    err = verify_taskset(tasks, declared, EXPECTED)
    assert err == "", f"valid taskset should pass, got: {err}"


def test_tampered_question_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "TAMPERED QUESTION"
    err = verify_taskset(tasks, declared, EXPECTED)
    assert "TASK_SET_HASH_MISMATCH" in err


def test_tampered_answer_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["gold_answer"] = "999"
    err = verify_taskset(tasks, declared, EXPECTED)
    assert "TASK_SET_HASH_MISMATCH" in err


def test_replace_task_keep_old_declared_hash_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "SWAPPED QUESTION"
    err = verify_taskset(tasks, declared, EXPECTED)  # old declared hash
    assert "TASK_SET_HASH_MISMATCH" in err


def test_change_task_and_declared_hash_still_fails():
    """Even if attacker updates the declared hash, the EXPECTED hash blocks it."""
    import hashlib

    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "SWAPPED QUESTION"
    # attacker also updates declared hash to match the tampered content
    blob = json.dumps([(t["task_id"], t["question"], t["gold_answer"]) for t in tasks], sort_keys=True)
    new_declared = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    err = verify_taskset(tasks, new_declared, EXPECTED)
    assert "TASK_SET_HASH_UNEXPECTED" in err, f"expected UNEXPECTED, got: {err}"


def test_duplicate_task_id_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[1]["task_id"] = tasks[0]["task_id"]
    # fix declared hash to match tampered content so hash check passes, then ID check fires
    import hashlib
    blob = json.dumps([(t["task_id"], t["question"], t["gold_answer"]) for t in tasks], sort_keys=True)
    err = verify_taskset(tasks, hashlib.sha256(blob.encode("utf-8")).hexdigest(), hashlib.sha256(blob.encode("utf-8")).hexdigest())
    assert "TASK_ID_DUPLICATE" in err


def test_wrong_order_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0], tasks[1] = tasks[1], tasks[0]
    import hashlib
    blob = json.dumps([(t["task_id"], t["question"], t["gold_answer"]) for t in tasks], sort_keys=True)
    h = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    err = verify_taskset(tasks, h, h)
    assert "TASK_ORDER_MISMATCH" in err


def test_missing_declared_hash_fails():
    tasks, _ = _load_tasks()
    err = verify_taskset(tasks, "", EXPECTED)
    assert "DECLARED_HASH_MISSING" in err


def test_missing_expected_hash_fails():
    tasks, declared = _load_tasks()
    err = verify_taskset(tasks, declared, "")
    assert "EXPECTED_HASH_MISSING" in err


def test_missing_field_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0].pop("gold_answer")
    import hashlib
    blob = json.dumps([(t["task_id"], t["question"], t.get("gold_answer")) for t in tasks], sort_keys=True)
    err = verify_taskset(tasks, hashlib.sha256(blob.encode("utf-8")).hexdigest(), hashlib.sha256(blob.encode("utf-8")).hexdigest())
    assert "TASK_FIELD_MISSING" in err


# ---- Task C: provenance audit reproducibility ----

def test_provenance_audit_script_reproducible(tmp_path):
    """Run the standalone audit script and verify it reproduces 0/35 matches."""
    script = ROOT / "scripts" / "level3_pilot_r31" / "audit_gsm8k_provenance.py"
    if not script.exists():
        pytest.skip("audit script not present")
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=str(ROOT),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((ROOT / "results" / "level3_pilot_r31" / "dataset_provenance_audit.json").read_text(encoding="utf-8"))
    assert out["official_record_count"] == 1319
    assert out["official_file_sha256"] == "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
    assert out["r3_task_count"] == 35
    assert out["official_match_count"] == 0
    assert out["synthetic_or_unmatched_count"] == 35
