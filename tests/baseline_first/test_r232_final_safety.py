"""R2.3.2 tests: integrity manifest fail-closed + Docker container cleanup."""
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

INPUTS = [
    "parentre_ledger_parentre-8aa3d61f.json",
    "paired_confirmation_set.json",
    "paired_experiment_results_corrected.json",
    "parent_reverification_results.json",
]


def _copy_inputs(tmp_path: Path) -> Path:
    for rel in INPUTS + ["rescore_input_integrity.json"]:
        src = RES / rel
        if src.exists():
            shutil.copy2(src, tmp_path / rel)
    return tmp_path


def _run_rescore(res_dir: Path):
    code = RESCORE.read_text(encoding="utf-8")
    code = code.replace('RES = ROOT / "results" / "level3_pilot_r2"', f'RES = Path(r"{res_dir}")')
    patched = res_dir / "rescore_patched.py"
    patched.write_text(code, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(patched)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60, cwd=str(ROOT),
    )


def test_valid_inputs_reproduce_frozen_stats(tmp_path):
    d = _copy_inputs(tmp_path)
    r = _run_rescore(d)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((d / "rescore_from_ledger.json").read_text(encoding="utf-8"))
    assert out["PARENT"]["correct"] == 11
    assert out["CHILD"]["correct"] == 11
    assert out["PAIRED"]["net_gain"] == 0


def test_missing_manifest_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    (d / "rescore_input_integrity.json").unlink()
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MANIFEST_MISSING" in (r.stdout or "")


def test_empty_manifest_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    (d / "rescore_input_integrity.json").write_text("{}", encoding="utf-8")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MANIFEST_EMPTY" in (r.stdout or "")


def test_manifest_missing_entry_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "rescore_input_integrity.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m.pop("paired_confirmation_set.json")
    p.write_text(json.dumps(m), encoding="utf-8")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MANIFEST_MISSING_ENTRIES" in (r.stdout or "")


def test_manifest_unauthorized_entry_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "rescore_input_integrity.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m["evil_extra.json"] = "0" * 64
    p.write_text(json.dumps(m), encoding="utf-8")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "MANIFEST_UNAUTHORIZED_ENTRIES" in (r.stdout or "")


def test_input_content_change_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_confirmation_set.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["tasks"][0]["question"] = "TAMPERED"
    p.write_text(json.dumps(data), encoding="utf-8")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "HASH_MISMATCH" in (r.stdout or "")


def test_byte_change_with_same_text_fails(tmp_path):
    d = _copy_inputs(tmp_path)
    p = d / "paired_confirmation_set.json"
    raw = p.read_bytes()
    p.write_bytes(raw + b"\n")
    r = _run_rescore(d)
    assert r.returncode != 0
    assert "HASH_MISMATCH" in (r.stdout or "")


def test_manifest_not_auto_created_by_rescore(tmp_path):
    d = _copy_inputs(tmp_path)
    (d / "rescore_input_integrity.json").unlink()
    r = _run_rescore(d)
    assert r.returncode != 0
    assert not (d / "rescore_input_integrity.json").exists()


def _graph_printing(n: int) -> str:
    return (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        f"        for i in range({n}):\n"
        "            print('x' * 100)\n"
        "        return 'done'\n"
    )


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


def _assert_cleanup_recorded(res, label):
    dc = res.get("docker_cleanup")
    assert dc is not None, f"{label}: docker_cleanup missing"
    assert "cleaned" in dc and "error" in dc, f"{label}: incomplete cleanup status"
    if dc.get("container_created", True):
        assert dc.get("container_id"), f"{label}: container_id missing but created"
    return dc


def _docker_container_gone(cid: str) -> bool:
    r = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", cid],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    return r.returncode != 0 or "false" in (r.stdout or "").lower()


def test_normal_execution_container_exits():
    from src.runtime.workflow_ipc import run_workflow_code_isolated

    g = ("class Workflow:\n    def __init__(self, llm=None):\n        self.llm = llm\n"
         "    async def __call__(self, problem):\n        return 'ok'\n")
    res = run_workflow_code_isolated(g, problem="q", task_id="t", gold_answer=None,
                                     llm=FakeLLM(), timeout=25)
    assert res["ok"] is True
    dc = _assert_cleanup_recorded(res, "normal")
    assert dc.get("container_created") is True
    assert dc.get("cleaned") is True
    assert _docker_container_gone(dc["container_id"])


def test_stdout_overflow_container_exits():
    from src.runtime.workflow_ipc import MAX_PIPE_BYTES, run_workflow_code_isolated

    n = (MAX_PIPE_BYTES // 100) + 100
    res = run_workflow_code_isolated(_graph_printing(n), problem="q", task_id="t",
                                     gold_answer=None, llm=FakeLLM(), timeout=30)
    assert res["ok"] is False
    dc = _assert_cleanup_recorded(res, "overflow")
    assert dc.get("container_created") is True
    assert _docker_container_gone(dc["container_id"])


def test_stderr_overflow_container_exits():
    from src.runtime.workflow_ipc import MAX_PIPE_BYTES, run_workflow_code_isolated

    g = ("class Workflow:\n    def __init__(self, llm=None):\n        self.llm = llm\n"
         "    async def __call__(self, problem):\n"
         "        import sys\n"
         f"        for i in range({(MAX_PIPE_BYTES // 100) + 100}):\n"
         "            print('e' * 100, file=sys.stderr)\n"
         "        return 'done'\n")
    res = run_workflow_code_isolated(g, problem="q", task_id="t", gold_answer=None,
                                     llm=FakeLLM(), timeout=30)
    assert res["ok"] is False
    dc = _assert_cleanup_recorded(res, "overflow")
    assert dc.get("container_created") is True
    assert _docker_container_gone(dc["container_id"])


def test_timeout_container_exits():
    from src.runtime.workflow_ipc import run_workflow_code_isolated

    g = ("class Workflow:\n    def __init__(self, llm=None):\n        self.llm = llm\n"
         "    async def __call__(self, problem):\n"
         "        import time\n        time.sleep(30)\n        return 'done'\n")
    res = run_workflow_code_isolated(g, problem="q", task_id="t", gold_answer=None,
                                     llm=FakeLLM(), timeout=5)
    assert res["ok"] is False
    dc = _assert_cleanup_recorded(res, "overflow")
    assert dc.get("container_created") is True
    assert _docker_container_gone(dc["container_id"])


def test_cleanup_failure_is_reported_and_not_scorable():
    import subprocess as _sp
    from src.runtime.workflow_ipc import run_workflow_code_isolated

    real_run = _sp.run

    def flaky_run(cmd, **kw):
        if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == "rm":
            class R:
                returncode = 1
                stdout = "Error: injected rm failure"
                stderr = ""
            return R()
        return real_run(cmd, **kw)

    _sp.run = flaky_run
    try:
        g = ("class Workflow:\n    def __init__(self, llm=None):\n        self.llm = llm\n"
             "    async def __call__(self, problem):\n        return 'ok'\n")
        res = run_workflow_code_isolated(g, problem="q", task_id="t", gold_answer=None,
                                         llm=FakeLLM(), timeout=25)
        dc = res.get("docker_cleanup") or {}
        assert dc.get("cleaned") is False
        assert "DOCKER_RM_FAILED" in str(dc.get("error", ""))
        assert res["ok"] is False
    finally:
        _sp.run = real_run


def test_container_not_created_distinguished():
    import subprocess as _sp
    from src.runtime.workflow_ipc import _run_bounded

    real_popen = _sp.Popen

    class FakePipe:
        def read(self, n=-1): return b""
        def close(self): pass

    class FakeProc:
        returncode = 125
        stdout = FakePipe()
        stderr = FakePipe()
        def wait(self, timeout=None): return 125
        def kill(self): pass

    _sp.Popen = lambda *a, **k: FakeProc()
    try:
        cmd = ["docker", "run", "python:3.10-slim", "python", "-c", "print(1)"]
        proc, out, err, overflow, dc = _run_bounded(cmd, timeout=10)
        assert dc.get("container_created") is False
        assert dc.get("error") == "CONTAINER_NOT_CREATED"
    finally:
        _sp.Popen = real_popen


def test_no_such_container_treated_as_cleaned():
    import subprocess as _sp
    from src.runtime.workflow_ipc import _run_bounded

    real_run = _sp.run

    def flaky_run(cmd, **kw):
        if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == "rm":
            class R:
                returncode = 1
                stdout = ""
                stderr = "Error: No such container: abc123"
            return R()
        return real_run(cmd, **kw)

    _sp.run = flaky_run
    try:
        cmd = ["docker", "run", "--rm", "python:3.10-slim", "python", "-c", "print(1)"]
        proc, out, err, overflow, dc = _run_bounded(cmd, timeout=20)
        assert dc.get("cleaned") is True
        assert dc.get("error") == "ALREADY_REMOVED"
    finally:
        _sp.run = real_run
