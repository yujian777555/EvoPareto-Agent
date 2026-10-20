"""Offline regression tests for the R3.1-R1 hash gate and provenance audit."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED = "ddf055537d4618c86d736d4f0ed98fd4b23efec21f9e0ffe65a2c8ee022a6219"
RES3 = ROOT / "results" / "level3_pilot_r3"
AUDIT_DIR = ROOT / "results" / "level3_pilot_r31"
SCRIPT = ROOT / "scripts" / "level3_pilot_r3" / "run_paired_35.py"
OFFICIAL_FILE = AUDIT_DIR / "gsm8k_test_official.jsonl"
R3_TASKSET = RES3 / "paired_confirmation_set_35.json"
AUDIT_OUTPUT = AUDIT_DIR / "dataset_provenance_audit.json"

spec = importlib.util.spec_from_file_location("r3_runner", SCRIPT)
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)
verify_taskset = rp.verify_taskset

audit_script = ROOT / "scripts" / "level3_pilot_r31" / "audit_gsm8k_provenance.py"
audit_spec = importlib.util.spec_from_file_location("r31_provenance", audit_script)
audit_module = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit_module)


def _load_manifest():
    return json.loads(R3_TASKSET.read_text(encoding="utf-8"))


def _load_tasks():
    conf = _load_manifest()
    return conf["tasks"], conf.get("task_set_sha256")


def _clone(tasks):
    return [dict(t) for t in tasks]


def _hash_tasks(tasks):
    blob = json.dumps(
        [(t["task_id"], t["question"], t["gold_answer"]) for t in tasks],
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ---- Task B: hash-gate regression ----

def test_valid_frozen_taskset_passes():
    tasks, declared = _load_tasks()
    assert verify_taskset(tasks, declared, EXPECTED) == ""


def test_tampered_question_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "TAMPERED QUESTION"
    assert "TASK_SET_HASH_MISMATCH" in verify_taskset(tasks, declared, EXPECTED)


def test_tampered_answer_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["gold_answer"] = "999"
    assert "TASK_SET_HASH_MISMATCH" in verify_taskset(tasks, declared, EXPECTED)


def test_replace_task_keep_old_declared_hash_fails():
    tasks, declared = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "SWAPPED QUESTION"
    assert "TASK_SET_HASH_MISMATCH" in verify_taskset(tasks, declared, EXPECTED)


def test_change_task_and_declared_hash_still_fails():
    tasks, _ = _load_tasks()
    tasks = _clone(tasks)
    tasks[0]["question"] = "SWAPPED QUESTION"
    new_declared = _hash_tasks(tasks)
    assert "TASK_SET_HASH_UNEXPECTED" in verify_taskset(tasks, new_declared, EXPECTED)


def test_duplicate_task_id_fails():
    tasks, _ = _load_tasks()
    tasks = _clone(tasks)
    tasks[1]["task_id"] = tasks[0]["task_id"]
    h = _hash_tasks(tasks)
    assert "TASK_ID_DUPLICATE" in verify_taskset(tasks, h, h)


def test_wrong_order_fails():
    tasks, _ = _load_tasks()
    tasks = _clone(tasks)
    tasks[0], tasks[1] = tasks[1], tasks[0]
    h = _hash_tasks(tasks)
    assert "TASK_ORDER_MISMATCH" in verify_taskset(tasks, h, h)


def test_missing_declared_hash_fails():
    tasks, _ = _load_tasks()
    assert "DECLARED_HASH_MISSING" in verify_taskset(tasks, "", EXPECTED)


def test_missing_expected_hash_fails():
    tasks, declared = _load_tasks()
    assert "EXPECTED_HASH_MISSING" in verify_taskset(tasks, declared, "")


def test_missing_field_fails():
    tasks, _ = _load_tasks()
    tasks = _clone(tasks)
    tasks[0].pop("gold_answer")
    h = _hash_tasks([{**t, "gold_answer": t.get("gold_answer")} for t in tasks])
    assert "TASK_FIELD_MISSING" in verify_taskset(tasks, h, h)


def test_invalid_taskset_stops_before_http(monkeypatch, tmp_path, capsys):
    """The real entry point must reject a bad manifest before any HTTP client."""
    conf = _load_manifest()
    conf["tasks"][0]["question"] += " tampered"
    (tmp_path / "paired_confirmation_set_35.json").write_text(
        json.dumps(conf), encoding="utf-8"
    )
    monkeypatch.setattr(rp, "OUT", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    def forbidden_http(*args, **kwargs):
        pytest.fail("HTTP client must not be created when the hash gate fails")

    monkeypatch.setattr(rp.urllib.request, "build_opener", forbidden_http)
    monkeypatch.setattr(rp.urllib.request, "urlopen", forbidden_http)
    assert rp.main() == 3
    assert "TASK_SET_HASH_MISMATCH" in capsys.readouterr().out


# ---- Task C: provenance reproducibility ----

def test_provenance_audit_reproduces_official_source_and_counts_without_writes():
    taskset_before = R3_TASKSET.read_bytes()
    audit_before = AUDIT_OUTPUT.read_bytes()
    summary = audit_module.audit_provenance()
    assert summary["official_record_count"] == 1319
    assert summary["official_file_sha256"] == "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
    assert summary["r3_task_count"] == 35
    assert summary["official_match_count"] == 0
    assert summary["synthetic_or_unmatched_count"] == 35
    assert summary["gold_mismatch_count"] == 0
    assert summary["gold_unverified_count"] == 0
    assert sum(summary[k] for k in (
        "official_match_count", "synthetic_or_unmatched_count",
        "gold_mismatch_count", "gold_unverified_count",
    )) == 35
    assert R3_TASKSET.read_bytes() == taskset_before
    assert AUDIT_OUTPUT.read_bytes() == audit_before


def test_question_match_without_extractable_gold_is_not_official():
    rows = audit_module.audit_task_rows(
        [{"task_id": "synthetic-1", "question": "  same   question ", "gold_answer": "42"}],
        [{"question": "same question", "answer": "reasoning with no final marker"}],
    )
    assert len(rows) == 1
    assert rows[0]["question_match"] == "EXACT"
    assert rows[0]["gold_match"] is None
    assert rows[0]["final_status"] == "GOLD_UNVERIFIED"


def test_official_file_hash_mismatch_fails_closed(tmp_path):
    bad_file = tmp_path / "tampered.jsonl"
    bad_file.write_bytes(OFFICIAL_FILE.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="OFFICIAL_FILE_SHA_MISMATCH"):
        audit_module.audit_provenance(official_path=bad_file)
