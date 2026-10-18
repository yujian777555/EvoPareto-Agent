"""Task B regression: output not truncated before scoring; cost not mistaken for answer."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.workflow_ipc import run_workflow_code_isolated


class FakeLLM:
    def _request(self, prompt: str) -> str:
        return "ok"

    async def __call__(self, prompt, **kw):
        return self._request(str(prompt))


# graph that returns a LONG response (>500 chars) with a clear boxed answer
LONG_GRAPH = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        text = 'x' * 600 + '\\n\\\\boxed{42}'\n"
    "        return text\n"
)

TUPLE_GRAPH = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        return ('The answer is \\\\boxed{17}', 0.0123)\n"
)

COST_TRAP_GRAPH = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        # intermediate numbers and a cost-like tail must NOT become the answer\n"
    "        return ('Step 1: 15 trees. Step 2: 21 trees. 21-15=6. \\\\boxed{6}', 0.0)\n"
)


def _run(graph: str):
    return run_workflow_code_isolated(
        graph, problem="What is 1+1?", task_id="t", gold_answer=None,
        llm=FakeLLM(), timeout=20,
    )


def test_long_response_not_truncated_in_scoring_payload():
    res = _run(LONG_GRAPH)
    assert res["ok"] is True, res
    out = res["stdout"]
    payload = json.loads(out[out.find("{"):])
    assert "answer_text" in payload
    assert payload["answer_len"] > 500, "response must not be truncated before scoring"
    assert "\\\\boxed{42}" in payload["answer_text"] or "\\boxed{42}" in payload["answer_text"]


def test_parent_tuple_response_separates_text_and_cost():
    res = _run(TUPLE_GRAPH)
    payload = json.loads(res["stdout"][res["stdout"].find("{"):])
    assert payload["out_kind"] == "tuple"
    assert "boxed{17}" in payload["answer_text"] or "17" in payload["answer_text"]
    assert payload["cost_meta"] is not None  # cost kept as metadata, not in the answer
    assert "0.0123" not in payload["answer_text"]


def test_cost_and_intermediate_numbers_not_mistaken_for_answer():
    res = _run(COST_TRAP_GRAPH)
    payload = json.loads(res["stdout"][res["stdout"].find("{"):])
    text = payload["answer_text"]
    # the extractor must find 6 (boxed), not 15/21/0
    from scripts.level3_pilot_r2.rescore_from_ledger import extract_boxed

    pred = extract_boxed(text)
    assert pred == "6", f"expected boxed 6, got {pred} from {text[:120]}"


def test_ledger_rows_contain_required_tracking_fields():
    led_path = ROOT / "results/level3_pilot_r2/parentre_ledger_parentre-8aa3d61f.json"
    if not led_path.exists():
        pytest.skip("ledger not present")
    data = json.loads(led_path.read_text(encoding="utf-8"))
    for row in data["rows"]:
        assert row.get("physical_request_id")
        assert row.get("prompt_sha256")
        assert row.get("request_phase")
        assert row.get("usage_prompt_tokens") is not None
        assert row.get("usage_completion_tokens") is not None
        assert row.get("finish_reason")
        assert row.get("FULL_CONTENT")  # full response preserved


def test_rescore_from_ledger_stats_consistent():
    p = ROOT / "results/level3_pilot_r2/rescore_from_ledger.json"
    if not p.exists():
        pytest.skip("rescore not present")
    d = json.loads(p.read_text(encoding="utf-8"))
    parent = d["PER_TASK_PARENT"]
    child = d["PER_TASK_CHILD"]
    assert len(parent) == 12 and len(child) == 12
    pc = sum(1 for r in parent if r["correct"])
    cc = sum(1 for r in child if r["correct"])
    assert pc == d["PARENT"]["correct"]
    assert cc == d["CHILD"]["correct"]
    paired = d["PAIRED"]
    assert paired["child_improved_over_parent"] + paired["child_regressed_vs_parent"] \
        + paired["both_correct"] + paired["both_wrong"] == 12
    assert paired["net_gain"] == cc - pc
    assert d["NEW_REAL_HTTP_REQUESTS"] == 0
