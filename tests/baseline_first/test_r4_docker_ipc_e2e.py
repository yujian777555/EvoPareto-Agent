"""Offline Docker/IPC E2E for R4 programs (SIMULATED_DOCKER_IPC only).

Uses the production entrypoint ``run_workflow_code_isolated`` with a local
deterministic llm test double. NEVER calls DeepSeek / HTTP with a real key.
Mock answers are SIMULATED_DOCKER_IPC evidence only — not REAL_MODEL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import (
    build_group_c_fixed_verify,
    compile_graph_source,
    load_frozen_parent,
    mutate_add_sampling,
)
from src.runtime.workflow_ipc import run_workflow_code_isolated

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
EVIDENCE = "SIMULATED_DOCKER_IPC"


class MockIPC:
    """Deterministic model double matching the R3 IPC contract."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def _request(self, prompt: str) -> str:
        self.calls.append(prompt)
        if not self._responses:
            return "Answer: 0"
        return self._responses.pop(0)

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def _extras_for_parent():
    return {
        "pydantic": "class BaseModel:\n    def __init__(self, **kw):\n        pass\ndef Field(default=None, **kw):\n    return default\n",
        "tenacity": "def retry(*a, **k):\n    return lambda f: f\ndef stop_after_attempt(*a, **k):\n    return None\ndef wait_fixed(*a, **k):\n    return None\ndef retry_if_exception_type(*a, **k):\n    return None\n",
        "workspace.GSM8K.workflows.template.operator": (
            "class Custom:\n"
            "    def __init__(self, llm):\n"
            "        self.llm = llm\n"
            "    async def __call__(self, input=None, instruction='', **kw):\n"
            "        prompt = (instruction + '\\n' + input) if instruction else input\n"
            "        # Match ModelIPCClient / AFlow contract: call_with_format or async call\n"
            "        if hasattr(self.llm, 'call_with_format'):\n"
            "            out = await self.llm.call_with_format(prompt)\n"
            "            return out\n"
            "        if hasattr(self.llm, '_request'):\n"
            "            out = self.llm._request(prompt)\n"
            "            if hasattr(out, '__await__'):\n"
            "                out = await out\n"
            "            return {'response': out}\n"
            "        out = await self.llm(prompt)\n"
            "        return {'response': out}\n"
        ),
        "workspace.GSM8K.workflows.round_1.prompt": "INSTRUCTION = ''\n",
        "scripts.async_llm": "def create_llm_instance(*a, **k):\n    return None\n",
        "scripts.evaluator": "class DatasetType:\n    pass\n",
        "prompt": "INSTRUCTION = ''\n",
    }


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(FROZEN)


def test_parent_identity_executes_in_docker_ipc(parent):
    graph = compile_graph_source(parent)
    llm = MockIPC(["Answer: 42"])
    res = run_workflow_code_isolated(
        graph,
        problem="What is 6*7?",
        task_id="ipc-parent-1",
        gold_answer=None,
        llm=llm,
        timeout=60,
        extra_modules=_extras_for_parent(),
    )
    assert res.get("ok") is True, res
    ans = res.get("answer_text")
    assert ans is not None
    assert "42" in str(ans)
    assert len(llm.calls) == 1
    assert "What is 6*7?" in llm.calls[0]
    assert res.get("docker_cleanup", {}).get("cleaned") in (True, None) or res.get("docker_cleanup")


def test_group_c_two_sequential_calls_stage2_sees_stage1(parent):
    c = build_group_c_fixed_verify(parent)
    graph = compile_graph_source(c)
    llm = MockIPC(["draft-stage1-answer", "Answer: 7"])
    res = run_workflow_code_isolated(
        graph,
        problem="2+2",
        task_id="ipc-c-1",
        gold_answer=None,
        llm=llm,
        timeout=60,
        extra_modules={},
    )
    assert res.get("ok") is True, res
    assert len(llm.calls) == 2, llm.calls
    # stage1 is Parent-style bare problem
    assert llm.calls[0].strip() == "2+2"
    # stage2 must carry stage1 output
    assert "draft-stage1-answer" in llm.calls[1]
    assert "2+2" in llm.calls[1]
    assert "Answer: 7" in str(res.get("answer_text"))


def test_mutated_sampling_candidate_executes(parent):
    s = mutate_add_sampling(parent, n_samples=3)
    graph = compile_graph_source(s)
    llm = MockIPC(["Answer: 1", "Answer: 2", "Answer: 1"])
    res = run_workflow_code_isolated(
        graph,
        problem="q",
        task_id="ipc-s-1",
        gold_answer=None,
        llm=llm,
        timeout=60,
        extra_modules={},
    )
    assert res.get("ok") is True, res
    assert len(llm.calls) == 3
    assert "1" in str(res.get("answer_text"))


def test_invalid_graph_rejected_cleanly():
    res = run_workflow_code_isolated(
        "x = 1\n",
        problem="q",
        task_id="ipc-bad",
        gold_answer=None,
        llm=MockIPC([]),
        timeout=30,
        extra_modules={},
    )
    # must not claim ok; must not leave a container if it never started
    assert res.get("ok") in (False, None)
    cleanup = res.get("docker_cleanup") or {}
    # if container was created it must be cleaned
    if cleanup.get("container_created"):
        assert cleanup.get("cleaned") is True


def test_structured_answer_and_no_gold_leak(parent):
    graph = compile_graph_source(parent)
    llm = MockIPC(["Answer: 99"])
    res = run_workflow_code_isolated(
        graph,
        problem="secret-problem",
        task_id="ipc-gold",
        gold_answer="SHOULD_NOT_LEAK",
        llm=llm,
        timeout=60,
        extra_modules=_extras_for_parent(),
    )
    assert res.get("ok") is True
    # gold must not appear in any prompt
    for c in llm.calls:
        assert "SHOULD_NOT_LEAK" not in c
    assert res.get("answer_text") is not None


def test_evidence_label_simulated_docker_ipc():
    assert EVIDENCE == "SIMULATED_DOCKER_IPC"
    assert EVIDENCE != "REAL_MODEL"
