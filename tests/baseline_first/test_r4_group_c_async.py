"""Group C async execution-contract tests (SIMULATED IPC only).

Covers: sequential awaited calls, stage-2 sees stage-1 answer, Parent stage-1
prompt equality, call counts, stage-1/2 exceptions, timeout, empty answers.
No network. No real model API.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import (
    GROUP_C_CHECK_INSTRUCTION,
    MutationError,
    build_group_c_fixed_verify,
    execute_program_locally,
    group_c_stage2_prompt,
    load_frozen_parent,
    mutate_insert_instruction,
    parent_stage1_prompt,
)

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(FROZEN)


@pytest.fixture()
def group_c(parent):
    return build_group_c_fixed_verify(parent)


def test_group_c_stage2_prompt_contains_problem_and_first_output():
    p = group_c_stage2_prompt("What is 2+2?", "draft: 2+2=4")
    assert GROUP_C_CHECK_INSTRUCTION in p
    assert "What is 2+2?" in p
    assert "First output: draft: 2+2=4" in p
    # must not be the bare problem
    assert p.strip() != "What is 2+2?"


def test_parent_stage1_prompt_empty_instruction_is_problem():
    assert parent_stage1_prompt("", "Q?") == "Q?"
    assert parent_stage1_prompt("Solve", "Q?") == "Solve\nQ?"


def test_group_c_sequential_two_real_calls(group_c):
    """Two calls complete; stage-2 input includes stage-1 answer; order preserved."""
    log = []

    def hook(prompt: str) -> str:
        log.append(prompt)
        if len(log) == 1:
            return "draft-answer-42"
        return "Answer: 42"

    res = execute_program_locally(group_c, "What is 6*7?", llm_hook=hook)
    assert res["ok"] is True, res
    assert res["n_llm_calls"] == 2
    assert res["request_log"] == log
    # stage 1 prompt = Parent-style (empty instruction -> bare problem)
    assert log[0] == "What is 6*7?"
    # stage 2 must carry first output
    assert "draft-answer-42" in log[1]
    assert GROUP_C_CHECK_INSTRUCTION in log[1]
    assert "What is 6*7?" in log[1]
    assert res["answer_text"] == "Answer: 42"


def test_group_c_stage1_prompt_matches_parent(parent, group_c):
    """Group C stage-1 prompt equals Parent prompt for the same problem."""
    problem = "A bakery made 200 loaves. How many left?"
    # Parent: instruction ""
    parent_prompt = parent_stage1_prompt(parent.instruction, problem)

    seen = []

    def hook(prompt: str) -> str:
        seen.append(prompt)
        return "x" if len(seen) == 1 else "Answer: 55"

    res = execute_program_locally(group_c, problem, llm_hook=hook)
    assert res["ok"] is True
    assert seen[0] == parent_prompt == problem


def test_group_c_async_ipc_hook(group_c):
    """Async _request-style hook (awaitable) works and is awaited."""
    calls = []

    class AsyncIPC:
        async def _request(self, prompt: str) -> str:
            calls.append(prompt)
            await asyncio.sleep(0)
            return "stage1-out" if len(calls) == 1 else "Answer: 7"

        def get_usage_summary(self):
            return {"total_cost": 0.0}

    # execute_program_locally wraps llm_hook; pass a function returning awaitable
    def hook(prompt: str):
        async def _go():
            return await AsyncIPC()._request(prompt)
        return _go()

    res = execute_program_locally(group_c, "2+2", llm_hook=hook)
    assert res["ok"] is True, res
    assert res["n_llm_calls"] == 2
    assert "stage1-out" in res["request_log"][1]


def test_group_c_stage1_exception(group_c):
    def hook(prompt: str) -> str:
        raise RuntimeError("SIMULATED_STAGE1_FAIL")

    res = execute_program_locally(group_c, "Q", llm_hook=hook)
    assert res["ok"] is False
    assert "WORKFLOW_CALL" in res["error"] or "GRAPH" in res["error"]
    assert res["n_llm_calls"] >= 1


def test_group_c_stage2_exception(group_c):
    n = {"i": 0}

    def hook(prompt: str) -> str:
        n["i"] += 1
        if n["i"] == 1:
            return "first"
        raise RuntimeError("SIMULATED_STAGE2_FAIL")

    res = execute_program_locally(group_c, "Q", llm_hook=hook)
    assert res["ok"] is False
    assert res["n_llm_calls"] == 2


def test_group_c_timeout(group_c):
    def hook(prompt: str):
        async def _slow():
            await asyncio.sleep(1.0)
            return "late"
        return _slow()

    res = execute_program_locally(group_c, "Q", llm_hook=hook, timeout_s=0.05)
    assert res["ok"] is False
    assert res["error"] == "WORKFLOW_TIMEOUT"
    assert res["evidence_class"] == "SIMULATED"


def test_group_c_empty_answers(group_c):
    def hook(prompt: str) -> str:
        return ""

    res = execute_program_locally(group_c, "Q", llm_hook=hook)
    # empty second stage still returns ok with empty text (scoring layer decides)
    assert res["evidence_class"] == "SIMULATED"
    if res["ok"]:
        assert res["answer_text"] == ""
    assert res["n_llm_calls"] == 2


def test_group_c_call_count_matches_log(group_c):
    seen = []

    def hook(prompt: str) -> str:
        seen.append(prompt)
        return "A%d" % len(seen)

    res = execute_program_locally(group_c, "P", llm_hook=hook)
    assert res["n_llm_calls"] == len(seen) == 2
    assert res["request_log"] == seen


def test_group_c_not_sampling(parent):
    with pytest.raises(MutationError, match="GROUP_C"):
        build_group_c_fixed_verify(parent.clone_with(aggregation="majority_vote", n_samples=3))
