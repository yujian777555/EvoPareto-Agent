"""R2.3.4 regression: container state, mandatory child hash, Popen failure."""
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


# ---- rescore tests ----

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


def test_child_sha_missing_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data.pop("child_graph_sha256", None)
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "CHILD_SHA_MISSING" in (r.stdout or "")


def test_child_sha_wrong_fails(tmp_path):
    d = _copy(tmp_path)
    p = d / "parent_reverification_results.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    data["child_graph_sha256"] = "f" * 64
    p.write_text(json.dumps(data), encoding="utf-8")
    _reinit(d)
    r = _run(d)
    assert r.returncode != 0
    assert "CHILD_SHA_MISMATCH" in (r.stdout or "")


def test_valid_inputs_reproduce_stats(tmp_path):
    d = _copy(tmp_path)
    r = _run(d)
    assert r.returncode == 0, r.stdout + r.stderr
    out = json.loads((d / "rescore_from_ledger.json").read_text(encoding="utf-8"))
    assert out["PARENT"]["correct"] == 11
    assert out["CHILD"]["correct"] == 11
    assert out["PAIRED"]["net_gain"] == 0


# ---- Popen failure tests ----

class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


def test_popen_failure_returns_not_scorable():
    import subprocess as _sp

    from src.runtime.workflow_ipc import _run_bounded

    real_popen = _sp.Popen

    def flaky_popen(*a, **k):
        raise OSError("injected popen failure")

    _sp.Popen = flaky_popen
    try:
        calls = {"cleanup_fn": False}

        def cleanup_fn():
            calls["cleanup_fn"] = True

        proc, out, err, overflow, dc = _run_bounded(
            ["docker", "run", "python:3.10-slim", "python", "-c", "print(1)"],
            timeout=10, cleanup_fn=cleanup_fn,
        )
        assert proc is None
        assert dc.get("container_created") is False
        assert "POPEN_FAILED" in str(dc.get("error", ""))
        assert calls["cleanup_fn"] is True, "cleanup_fn must be called on Popen failure"
    finally:
        _sp.Popen = real_popen


def test_no_cid_still_calls_cleanup_fn():
    from src.runtime.workflow_ipc import _run_bounded
    import subprocess as _sp

    real_popen = _sp.Popen

    class FakePipe:
        def read(self, n=-1):
            return b""

        def close(self):
            pass

    class FakeProc:
        returncode = 125
        stdout = FakePipe()
        stderr = FakePipe()

        def wait(self, timeout=None):
            return 125

        def kill(self):
            pass

    _sp.Popen = lambda *a, **k: FakeProc()
    try:
        calls = {"cleanup_fn": False}

        def cleanup_fn():
            calls["cleanup_fn"] = True

        proc, out, err, overflow, dc = _run_bounded(
            ["docker", "run", "python:3.10-slim", "python", "-c", "print(1)"],
            timeout=10, cleanup_fn=cleanup_fn,
        )
        assert dc.get("container_created") is False
        assert dc.get("error") == "CONTAINER_NOT_CREATED"
        assert calls["cleanup_fn"] is True, "cleanup_fn must be called when no container"
    finally:
        _sp.Popen = real_popen


def test_cleanup_failure_blocks_scoring():
    import subprocess as _sp

    from src.runtime.workflow_ipc import run_workflow_code_isolated

    real_run = _sp.run

    def flaky_run(cmd, **kw):
        if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == "rm":
            class R:
                returncode = 1
                stdout = "Error: injected"
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
        assert res["ok"] is False, "cleanup failure must not be scorable"
    finally:
        _sp.run = real_run
