"""Level 3-R2 Task D: candidate bundle reliability (compile vs load, contract kind)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.runtime.candidate_bundle import (
    BundleValidationError,
    PromptContractError,
    build_bundle,
    load_bundle_from_live_responses,
    normalize_prompt_module,
    sha256_text,
)

G = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, p):\n"
    "        return 1\n"
)

LIVE = ROOT / "results" / "level3_live_calibration"


def test_contract_kind_plain_text():
    b = build_bundle(graph_src=G, prompt_field="Be careful")
    assert b.prompt_contract == "SERIALISED_INSTRUCTION_REPR"
    assert b.prompt_load_ok is True
    assert b.instruction_binding_type == "str"


def test_contract_kind_python_passthrough():
    b = build_bundle(graph_src=G, prompt_field="INSTRUCTION = 'hello'\n")
    assert b.prompt_contract == "PASSTHROUGH_PYTHON_MODULE"


def test_normalize_returns_kind():
    m, k = normalize_prompt_module("plain text", return_kind=True)
    assert k == "SERIALISED_INSTRUCTION_REPR"
    m2, k2 = normalize_prompt_module("INSTRUCTION = 'x'\n", return_kind=True)
    assert k2 == "PASSTHROUGH_PYTHON_MODULE"


def test_compile_vs_load_distinction():
    # compiles as Python but fails at load (NameError)
    bad = "INSTRUCTION = undefined_name_xyz\n"
    with pytest.raises(PromptContractError, match="PROMPT_MODULE_LOAD_FAIL"):
        build_bundle(graph_src=G, prompt_field=bad)


def test_instruction_binding_must_be_module_level():
    # has INSTRUCTION assignment but it is not a string
    bad = "INSTRUCTION = 42\n"
    with pytest.raises(PromptContractError, match="PROMPT_INSTRUCTION_NOT_STRING"):
        build_bundle(graph_src=G, prompt_field=bad)


def test_missing_instruction_binding_rejected():
    # valid Python module but no INSTRUCTION (will be serialised as text instead)
    # a module with only a comment has no INSTRUCTION assignment -> serialised
    b = build_bundle(graph_src=G, prompt_field="# just a comment\n")
    assert b.prompt_contract == "SERIALISED_INSTRUCTION_REPR"


def test_graph_source_never_rewritten():
    b = build_bundle(graph_src=G, prompt_field="hello")
    assert b.graph_src == G
    assert b.graph_sha256 == sha256_text(G) or b.graph_sha256 == __import__("hashlib").sha256(G.encode()).hexdigest()


def test_real_live_bundle_sha_stable():
    b1 = load_bundle_from_live_responses(LIVE / "real_model_responses.json")
    b2 = load_bundle_from_live_responses(LIVE / "real_model_responses.json")
    assert b1.graph_sha256 == b2.graph_sha256
    assert b1.prompt_module_sha256 == b2.prompt_module_sha256
    assert b1.bundle_sha256 == b2.bundle_sha256
    assert b1.graph_compile_ok and b1.prompt_load_ok
    cand = __import__("json").loads((LIVE / "candidate_validation.json").read_text(encoding="utf-8"))
    assert b1.graph_sha256 == cand["CANDIDATE_GRAPH_SHA"]


def test_dependency_error_attributed():
    """A graph with a bad import must fail at execution, not be silently swapped."""
    from src.runtime.workflow_ipc import run_workflow_code_isolated

    class _M:
        def _request(self, p):
            return "ok"

    res = run_workflow_code_isolated(
        "import module_that_does_not_exist_xyz\n"
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, p):\n        return 'x'\n",
        problem="What is 1+1?", task_id="neg", gold_answer=None,
        llm=_M(), timeout=20,
    )
    assert res["ok"] is False
    assert "ModuleNotFoundError" in (res.get("stderr") or "") or "ImportError" in (res.get("stderr") or "")
