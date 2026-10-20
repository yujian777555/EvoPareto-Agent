"""R2.3.5 E2E: Popen failure and cleanup_fn observability via public entry."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import run_workflow_code_isolated


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


GRAPH = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n        self.llm = llm\n"
    "    async def __call__(self, problem):\n        return 'ok'\n"
)


def _run(**kw):
    return run_workflow_code_isolated(
        GRAPH, problem="q", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=25, **kw,
    )


def test_popen_failure_returns_structured_failure_not_attributeerror():
    """Popen failure must yield a structured failure, not AttributeError."""
    import subprocess as _sp

    real_popen = _sp.Popen

    def flaky_popen(*a, **k):
        raise OSError("injected popen failure")

    _sp.Popen = flaky_popen
    try:
        res = _run()
        assert res["ok"] is False
        assert res["answer_text"] is None
        assert "POPEN_FAILED" in str(res.get("error", ""))
        assert "docker_cleanup" in res
    finally:
        _sp.Popen = real_popen


def test_popen_failure_cleanup_fn_executes():
    """cleanup_fn must run even when Popen fails before container creation."""
    import subprocess as _sp

    real_popen = _sp.Popen
    calls = {"cleanup_fn": 0}

    def flaky_popen(*a, **k):
        raise OSError("injected popen failure")

    _sp.Popen = flaky_popen
    try:
        def cleanup_fn():
            calls["cleanup_fn"] += 1

        res = run_workflow_code_isolated(
            GRAPH, problem="q", task_id="t", gold_answer=None,
            llm=FakeLLM(), timeout=25, cleanup_fn=cleanup_fn,
        )
        assert res["ok"] is False
        assert calls["cleanup_fn"] == 1
    finally:
        _sp.Popen = real_popen


def test_cleanup_fn_exception_recorded_not_silent():
    """cleanup_fn exception must be recorded, not swallowed."""
    import subprocess as _sp

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
        def bad_cleanup():
            raise RuntimeError("cleanup callback exploded")

        res = run_workflow_code_isolated(
            GRAPH, problem="q", task_id="t", gold_answer=None,
            llm=FakeLLM(), timeout=25, cleanup_fn=bad_cleanup,
        )
        dc = res.get("docker_cleanup") or {}
        assert "CLEANUP_FN_EXCEPTION" in str(dc.get("error", "")) or \
               "DOCKER_RM_FAILED" in str(dc.get("error", ""))
        assert res["ok"] is False, "cleanup failure must not be scorable"
    finally:
        _sp.run = real_run


def test_cleanup_fn_success_consistent_with_state():
    """Normal run: cleanup_fn executes and result matches actual state."""
    calls = {"cleanup_fn": 0}

    def cleanup_fn():
        calls["cleanup_fn"] += 1

    res = run_workflow_code_isolated(
        GRAPH, problem="q", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=25, cleanup_fn=cleanup_fn,
    )
    assert res["ok"] is True
    dc = res.get("docker_cleanup") or {}
    assert dc.get("cleaned") is True or dc.get("container_created") is False
    assert calls["cleanup_fn"] == 1


def test_no_cid_path_calls_cleanup_fn():
    """CONTAINER_NOT_CREATED path must still run cleanup_fn."""
    import subprocess as _sp

    real_popen = _sp.Popen
    calls = {"cleanup_fn": 0}

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
        def cleanup_fn():
            calls["cleanup_fn"] += 1

        res = run_workflow_code_isolated(
            GRAPH, problem="q", task_id="t", gold_answer=None,
            llm=FakeLLM(), timeout=25, cleanup_fn=cleanup_fn,
        )
        assert calls["cleanup_fn"] == 1
        assert res["ok"] is False
    finally:
        _sp.Popen = real_popen
