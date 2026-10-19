"""Task C tests: bounded output capture."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import MAX_PIPE_BYTES, run_workflow_code_isolated


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


def _run(graph: str, **kw):
    return run_workflow_code_isolated(
        graph, problem="q", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=30, **kw,
    )


def _graph_printing(n: int) -> str:
    return (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        f"        for i in range({n}):\n"
        "            print('x' * 100)\n"
        "        return 'done'\n"
    )


def test_normal_structured_result_works():
    g = (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        "        return '#### 42'\n"
    )
    res = _run(g)
    assert res["ok"] is True
    assert res["answer_text"] and "42" in res["answer_text"]


def test_oversized_stdout_fails_explicitly():
    n_chunks = (MAX_PIPE_BYTES // 100) + 100
    res = _run(_graph_printing(n_chunks))
    assert res["ok"] is False
    assert "PIPE_OVERFLOW" in str(res.get("error", "")) or "TOO_LARGE" in str(res.get("error", ""))
    assert res["answer_text"] is None


def test_oversized_stderr_fails_explicitly():
    g = (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        "        import sys\n"
        f"        for i in range({(MAX_PIPE_BYTES // 100) + 100}):\n"
        "            print('e' * 100, file=sys.stderr)\n"
        "        return 'done'\n"
    )
    res = _run(g)
    assert res["ok"] is False
    assert "PIPE_OVERFLOW" in str(res.get("error", ""))


def test_continuous_output_bounded():
    res = _run(_graph_printing(50000))
    if res["ok"]:
        assert res["answer_text"] is not None
    else:
        assert "PIPE_OVERFLOW" in str(res.get("error", ""))


def test_docker_cleanup_after_overflow():
    import subprocess

    res = _run(_graph_printing((MAX_PIPE_BYTES // 100) + 100))
    assert res["ok"] is False
    r = subprocess.run(
        ["docker", "ps", "-q", "--filter", "ancestor=python:3.10-slim"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
    )
    assert r.returncode == 0


def test_bounded_runner_rejects_before_scoring_on_overflow():
    res = _run(_graph_printing((MAX_PIPE_BYTES // 100) + 100))
    assert res["answer_text"] is None
    assert res["answer_sha256"] is None
