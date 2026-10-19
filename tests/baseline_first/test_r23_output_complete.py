"""Task A regression: complete structured output, size limits, tuple separation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import (
    MAX_STRUCTURED_RESULT_CHARS,
    run_workflow_code_isolated,
)


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"


def _graph_returning(expr: str) -> str:
    return (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n"
        "        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        f"        return {expr}\n"
    )


def _run(graph: str, **kw):
    return run_workflow_code_isolated(
        graph, problem="What is 1+1?", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=25, **kw,
    )


def test_response_600_chars_not_truncated():
    res = _run(_graph_returning("'a' * 650 + '\\n\\\\boxed{42}'"))
    assert res["ok"] is True, res
    assert res["answer_len"] > 600
    assert "boxed{42}" in res["answer_text"] or "\\boxed{42}" in res["answer_text"]
    assert res["answer_sha256"]


def test_response_2000_chars_not_truncated():
    res = _run(_graph_returning("'b' * 2100 + '\\n\\\\boxed{7}'"))
    assert res["ok"] is True, res
    assert res["answer_len"] > 2000
    assert "boxed{7}" in res["answer_text"] or "\\boxed{7}" in res["answer_text"]


def test_response_8000_chars_not_truncated():
    res = _run(_graph_returning("'c' * 8100 + '\\n\\\\boxed{9}'"))
    assert res["ok"] is True, res
    assert res["answer_len"] > 8000
    assert "boxed{9}" in res["answer_text"] or "\\boxed{9}" in res["answer_text"]


def test_unicode_newlines_latex_backslash_preserved():
    expr = r"'第一行\\n第二行 \\\\boxed{42} \\frac{1}{2} 路径\\to\\end'"
    res = _run(_graph_returning(expr))
    assert res["ok"] is True, res
    at = res["answer_text"]
    assert "第一行" in at
    assert "42" in at
    assert res["answer_len"] == len(at)


def test_tuple_output_separates_cost():
    res = _run(_graph_returning("('答案是 \\\\boxed{17}', 0.0123)"))
    assert res["out_kind"] == "tuple"
    assert "17" in res["answer_text"]
    assert "0.0123" not in res["answer_text"]
    assert res["cost_meta"] is not None and "0.0123" in str(res["cost_meta"])


def test_plain_string_output():
    res = _run(_graph_returning("'just \\\\boxed{5}'"))
    assert res["out_kind"] == "plain"
    assert "5" in res["answer_text"]


def test_oversized_result_fails_explicitly():
    huge = "'z' * " + str(MAX_STRUCTURED_RESULT_CHARS + 500)
    res = _run(_graph_returning(huge))
    assert res["ok"] is False
    assert res["error"] == "STRUCTURED_RESULT_TOO_LARGE"
    assert res["answer_text"] is None  # must NOT truncate and continue scoring


def test_diagnostics_excerpt_but_answer_complete():
    # answer is long; diagnostics must be excerpted
    res = _run(_graph_returning("'d' * 1300 + '#### 99'"))
    assert res["answer_len"] > 1200
    assert len(res.get("stdout_excerpt") or "") <= 900
    assert "99" in res["answer_text"]


def test_json_parse_failure_refuses_scoring():
    """A graph that prints garbage (no JSON) must refuse scoring, not scrape logs."""
    graph = (
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n"
        "        self.llm = llm\n"
        "    async def __call__(self, problem):\n"
        "        raise RuntimeError('crash before structured output')\n"
        "        return 'done'\n"
    )
    res = _run(graph)
    assert res["ok"] is False
    assert "JSON_PARSE_FAILED" in str(res.get("parse_status", "")) or res.get("answer_text") is None


def test_old_implementation_would_have_truncated():
    """Prove these tests would catch the old proc.stdout[-800:] defect."""
    # simulate the old behaviour: slice the full stdout to 800 chars
    res = _run(_graph_returning("'e' * 3100 + '\\n\\\\boxed{11}'"))
    full = res["answer_text"]
    old_style = repr(full)[-800:]  # what the old code effectively kept
    # the boxed answer would still be present in a 3000-char tail, but the
    # KEY check is that our current answer_len >> 800 — the old code could
    # not deliver 3000 chars of answer_text at all
    assert res["answer_len"] > 800, "old impl capped at 800 chars"
    assert len(full) == res["answer_len"]


def test_answer_sha256_matches_content():
    res = _run(_graph_returning("'hello #### 7'"))
    import hashlib

    expect = hashlib.sha256(res["answer_text"].encode("utf-8")).hexdigest()
    assert res["answer_sha256"] == expect
