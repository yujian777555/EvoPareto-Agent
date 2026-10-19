"""Task C tests: strict re-verification metadata cross-checks."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RES = ROOT / "results" / "level3_pilot_r2"
RESCORE = ROOT / "scripts" / "level3_pilot_r2" / "rescore_from_ledger.py"
INPUTS = [
    "parentre_ledger_parentre-8aa3d61f.json",
    "paired_confirmation_set.json",
    "paired_experiment_results_corrected.json",
    "parent_reverification_results.json",
]


def _copy(tmp_path):
    for rel in INPUTS + ["rescore_input_integrity.json"]:
        src = RES / rel
        if src.exists():
            shutil.copy2(src, tmp_path / rel)
    return tmp_path


def _reinit(res_dir):
    import importlib.util

    spec = importlib.util.spec_from_file_location("rs", RESCORE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    (res_dir / "rescore_input_integrity.json").unlink(missing_ok=True)
    mod.init_integrity_manifest(res_dir)


def _run(res_dir):
    code = RESCORE.read_text(encoding="utf-8")
    code = code.replace('RES = ROOT / "results" / "level3_pilot_r2"', f'RES = Path(r"{res_dir}")')
    patched = res_dir / "rs.py"
    patched.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(patched)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=60, cwd=str(ROOT),
    )


def test_valid_metadata_passes(tmp_path):
    d = _copy(tmp_path)
    r = _run(d)
    assert r.returncode == 0, r.stdout + r.stderr


def test_missing_top_run_id_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data.pop("run_id", None)
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "RUN_ID_MISMATCH" in (r.stdout or "") or "RUN_ID_MISSING" in (r.stdout or "")


def test_wrong_top_run_id_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["run_id"] = "wrong-run-id"
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "RUN_ID_MISMATCH" in (r.stdout or "")


def test_missing_per_record_run_id_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    per = data.get("PER_TASK_PARENT") or data.get("PER_TASK")
    per[0].pop("run_id", None)
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "RUN_ID_MISSING" in (r.stdout or "")


def test_missing_top_taskset_hash_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data.pop("task_set_sha256", None)
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "TASKSET_HASH_MISMATCH" in (r.stdout or "")


def test_wrong_top_child_sha_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["child_graph_sha256"] = "0" * 64
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "CHILD_SHA_MISMATCH" in (r.stdout or "")


def test_duplicate_task_ids_in_reverification_fails(tmp_path):
    """Duplicate task IDs (not just swapped order) must fail."""
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    per = data.get("PER_TASK_PARENT") or data.get("PER_TASK")
    per[1]["task_id"] = per[0]["task_id"]  # real duplicate
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0


def test_wrong_task_order_fails(tmp_path):
    """Swapped order (distinct from duplicate IDs) must fail."""
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    per = data.get("PER_TASK_PARENT") or data.get("PER_TASK")
    per[0], per[1] = per[1], per[0]  # swap, IDs stay unique
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "ORDER_MISMATCH" in (r.stdout or "") or "MAPPING_UNRESOLVED" in (r.stdout or "")
