"""Task A regression: rescore fail-closed logic and integrity checks."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RES = ROOT / "results" / "level3_pilot_r2"
RESCORE = ROOT / "scripts" / "level3_pilot_r2" / "rescore_from_ledger.py"


def _copy_inputs(tmp_path: Path) -> Path:
    """Copy all inputs into a temp res dir so we can tamper safely."""
    for rel in (
        "parentre_ledger_parentre-8aa3d61f.json",
        "paired_confirmation_set.json",
        "paired_experiment_results_corrected.json",
        "parent_reverification_results.json",
        "rescore_input_integrity.json",
    ):
        src = RES / rel
        if src.exists():
            dst = tmp_path / rel
            shutil.copy2(src, dst)
    return tmp_path


def _run_rescore(res_dir: Path, script: Path | None = None):
    """Run the rescore with RES pointing at res_dir."""
    s = script or RESCORE
    code = s.read_text(encoding="utf-8")
    # patch the module-level RES/ROOT constants to the temp dir
    code = code.replace('RES = ROOT / "results" / "level3_pilot_r2"', f'RES = Path(r"{res_dir}")')
    patched = res_dir / "rescore_patched.py"
    patched.write_text(code, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(patched)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, cwd=str(ROOT),
    )
    return r



def _reinit_manifest(res_dir: Path):
    """Re-init the manifest AFTER tampering so downstream checks are exercised."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("rs", RESCORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (res_dir / "rescore_input_integrity.json").unlink(missing_ok=True)
    mod.init_integrity_manifest(res_dir)


def test_valid_inputs_reproduce_frozen_stats(tmp_path):
    d = _copy_inputs(tmp_path)
    r = _run_rescore(d)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((d / "rescore_from_ledger.json").read_text(encoding="utf-8"))
    assert out["PARENT"]["correct"] == 11
    assert out["CHILD"]["correct"] == 11
    assert out["PAIRED"]["net_gain"] == 0


def test_missing_parent_reverification_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    (d / "parent_reverification_results.json").unlink()
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MISSING_INPUT" in (r.stdout or "") or "MISSING_INPUT" in (r.stderr or "")


def test_tampered_child_graph_hash_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_experiment_results_corrected.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["child_graph_sha256"] = "0" * 64
    p.write_text(json.dumps(data), encoding="utf-8")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "CHILD_SHA_MISMATCH" in (r.stdout or "") or "HASH_MISMATCH" in (r.stdout or "")


def test_tampered_task_content_with_old_hash_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_confirmation_set.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["tasks"][0]["question"] = "TAMPERED QUESTION CONTENT"
    # keep the OLD declared hash
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit_manifest(d)
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "TASK_SET_HASH_MISMATCH" in (r.stdout or "")


def test_missing_child_prediction_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_experiment_results_corrected.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for r in data["PER_TASK"]:
        if r["role"] == "child":
            r.pop("predicted_rescored", None)
            r.pop("predicted", None)
            break
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit_manifest(d)
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "CHILD_RESULT_INCOMPLETE" in (r.stdout or "")


def test_all_empty_run_ids_fail(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "parentre_ledger_parentre-8aa3d61f.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for row in data["rows"]:
        row["run_id"] = ""
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit_manifest(d)
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MAPPING_UNRESOLVED" in (r.stdout or "") or "RUN_ID" in (r.stdout or "")


def test_duplicate_physical_request_ids_fail(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "parentre_ledger_parentre-8aa3d61f.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["rows"][1]["physical_request_id"] = data["rows"][0]["physical_request_id"]
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit_manifest(d)
    r = _run_rescore(d)
    assert r.returncode != 0


def test_duplicate_task_ids_fail(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "parentre_ledger_parentre-8aa3d61f.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    # make all rows the same pid would already fail; use wrong task order instead
    p2 = d / "parent_reverification_results.json"
    rev = json.loads(p2.read_text(encoding="utf-8"))
    per = rev.get("PER_TASK_PARENT") or rev.get("PER_TASK")
    if per and len(per) >= 2:
        per[0], per[1] = per[1], per[0]  # wrong order
        p2.write_text(json.dumps(rev), encoding="utf-8")
        _reinit_manifest(d)
        r = _run_rescore(d)
        assert r.returncode != 0
        assert "ORDER_MISMATCH" in (r.stdout or "") or "MAPPING_UNRESOLVED" in (r.stdout or "")


def test_input_hash_change_detected(tmp_path):
    d = _copy_inputs(tmp_path)
    # run once to write the manifest
    r1 = _run_rescore(d)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    # tamper a file AFTER the manifest is written
    p = d / "paired_confirmation_set.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["tasks"][0]["gold_answer"] = "999"
    p.write_text(json.dumps(data), encoding="utf-8")
    r2 = _run_rescore(d)
    assert r2.returncode != 0
    assert "HASH_MISMATCH" in (r2.stdout or "") or "TASK_SET_HASH_MISMATCH" in (r2.stdout or "")


def test_correctness_conflict_detected(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_experiment_results_corrected.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    for r in data["PER_TASK"]:
        if r["role"] == "child":
            if "correct_rescored" in r:
                r["correct_rescored"] = not bool(r["correct_rescored"])
            else:
                r["correct"] = not bool(r.get("correct"))
            break
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit_manifest(d)
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "CONFLICT" in (r.stdout or "") or "HASH_MISMATCH" in (r.stdout or "")
