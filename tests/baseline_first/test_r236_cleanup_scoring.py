"""R2.3.6 E2E: cleanup_fn exception recording + fail-closed scoring."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import run_workflow_code_isolated

GRAPH = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        return '#### 42'\n"
)


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


def _run(**kw):
    return run_workflow_code_isolated(
        GRAPH, problem="q", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=25, **kw,
    )


# ---- Task A: cleanup_fn exception recording ----

def test_docker_rm_ok_cleanup_fn_ok():
    calls = {"n": 0}

    def good():
        calls["n"] += 1

    res = _run(cleanup_fn=good)
    dc = res.get("docker_cleanup") or {}
    assert calls["n"] == 1
    assert dc.get("cleaned") is True
    assert res["ok"] is True


def test_docker_rm_ok_cleanup_fn_raises():
    """error is None (rm succeeded) -> cleanup_fn exception must be recorded."""
    calls = {"n": 0}

    def bad():
        calls["n"] += 1
        raise RuntimeError("callback exploded")

    res = _run(cleanup_fn=bad)
    dc = res.get("docker_cleanup") or {}
    assert calls["n"] == 1
    assert "CLEANUP_FN_EXCEPTION" in str(dc.get("error", ""))
    assert dc.get("cleaned") is False
    assert res["ok"] is False, "cleanup failure must block scoring"


def test_docker_rm_fails_cleanup_fn_raises():
    import subprocess as _sp

    real = _sp.run

    def flaky(cmd, **kw):
        if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == "rm":
            class R:
                returncode = 1
                stdout = "Error: injected rm failure"
                stderr = ""
            return R()
        return real(cmd, **kw)

    _sp.run = flaky
    try:
        calls = {"n": 0}

        def bad():
            calls["n"] += 1
            raise RuntimeError("callback exploded")

        res = _run(cleanup_fn=bad)
        dc = res.get("docker_cleanup") or {}
        assert calls["n"] == 1
        err = str(dc.get("error", ""))
        assert "DOCKER_RM_FAILED" in err or "CLEANUP_FN_EXCEPTION" in err
        assert dc.get("cleaned") is False
        assert res["ok"] is False
    finally:
        _sp.run = real


def test_popen_fails_cleanup_fn_raises():
    import subprocess as _sp

    real_popen = _sp.Popen
    calls = {"n": 0}

    def flaky(*a, **k):
        raise OSError("injected popen failure")

    _sp.Popen = flaky
    try:
        def bad():
            calls["n"] += 1
            raise RuntimeError("callback exploded")

        res = _run(cleanup_fn=bad)
        dc = res.get("docker_cleanup") or {}
        assert calls["n"] == 1
        err = str(dc.get("error", ""))
        assert "CLEANUP_FN_EXCEPTION" in err or "POPEN_FAILED" in err
        assert res["ok"] is False
    finally:
        _sp.Popen = real_popen


# ---- Task B: fail-closed scoring ----

def test_no_cid_valid_answer_json_must_not_score():
    """rc=0 + valid answer JSON but no CID file -> ok=False."""
    import subprocess as _sp

    real_popen = _sp.Popen

    class FakePipe:
        def __init__(self, data=b""):
            self._data = data

        def read(self, n=-1):
            d, self._data = self._data, b""
            return d

        def close(self):
            pass

    class FakeProc:
        returncode = 0
        stdout = FakePipe(b'{"ok": true, "answer_text": "#### 42", "answer_len": 7, "out_kind": "plain", "task_id": "t", "task_keys": ["question", "task_id"], "question_len": 1}')
        stderr = FakePipe(b"")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    _sp.Popen = lambda *a, **k: FakeProc()
    try:
        res = _run()
        assert res["ok"] is False, "CONTAINER_NOT_CREATED must not score even with valid answer"
        assert res.get("answer_text") is not None or res.get("error")
    finally:
        _sp.Popen = real_popen


def test_container_created_and_cleaned_scores():
    res = _run()
    dc = res.get("docker_cleanup") or {}
    assert dc.get("container_created") is True
    assert dc.get("cleaned") is True
    assert res["ok"] is True
    assert res["answer_text"] is not None


def test_container_created_cleanup_fails_no_score():
    import subprocess as _sp

    real = _sp.run

    def flaky(cmd, **kw):
        if isinstance(cmd, list) and len(cmd) >= 3 and cmd[1] == "rm":
            class R:
                returncode = 1
                stdout = "Error: injected rm failure"
                stderr = ""
            return R()
        return real(cmd, **kw)

    _sp.run = flaky
    try:
        res = _run()
        dc = res.get("docker_cleanup") or {}
        assert dc.get("container_created") is True
        assert dc.get("cleaned") is False
        assert res["ok"] is False
    finally:
        _sp.run = real


def test_docker_check_failure_not_gone():
    """Daemon-unavailable must not be treated as container gone."""
    from tests.baseline_first.test_r232_final_safety import (
        DockerCheckError,
        _docker_container_state,
    )

    import subprocess as _sp

    real = _sp.run

    def flaky(cmd, **kw):
        class R:
            returncode = 1
            stdout = ""
            stderr = "Cannot connect to the Docker daemon"
        return R()

    _sp.run = flaky
    try:
        with pytest.raises(DockerCheckError):
            _docker_container_state("abc123")
    finally:
        _sp.run = real
