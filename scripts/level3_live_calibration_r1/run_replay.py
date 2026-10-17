"""Level 3-R1 deterministic replay of the saved real candidate (Task C).

No Optimizer call. No real DeepSeek. The exact graph/prompt bytes saved from
the live calibration are re-bundled and executed with a deterministic Mock IPC.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "level3_live_calibration_r1"
OUT.mkdir(parents=True, exist_ok=True)
LIVE = ROOT / "results" / "level3_live_calibration"

from src.runtime.candidate_bundle import (  # noqa: E402
    BundleValidationError,
    PromptContractError,
    build_bundle,
    load_bundle_from_live_responses,
    sha256_text,
)
from src.runtime.workflow_ipc import run_workflow_code_isolated  # noqa: E402
from src.benchmark.gsm8k_tasks import evaluate_workflow_output, load_offline_tasks  # noqa: E402


class MockIPC:
    """Deterministic gold-blind model for offline replay (NOT real DeepSeek)."""

    def _request(self, prompt: str) -> str:
        import re

        nums = re.findall(r"-?\d+", str(prompt))
        return "The final answer is #### " + (nums[0] if nums else "0")

    async def __call__(self, prompt, **kw):
        return self._request(str(prompt))

    async def call_with_format(self, prompt, formatter=None):
        raw = self._request(str(prompt))
        return {"response": raw, "modification": "mock", "graph": raw, "prompt": ""}

    def get_usage_summary(self):
        return {"total_cost": 0.0, "channel": "mock-ipc-replay"}


def _collect_modules(prompt_module: str, round_name: str = "round_2") -> dict:
    import types

    mods: Dict[str, str] = {}
    # dependency stubs (same as live path)
    generic = (
        "class BaseModel:\n"
        "    def __init__(self, **kw):\n"
        "        pass\n"
        "def Field(default=None, **kw):\n"
        "    return default\n"
        "def create_model(name, **kw):\n"
        "    return type(name, (BaseModel,), {})\n"
        "def to_jsonable_python(x, **k):\n"
        "    return x\n"
    )
    mods["pydantic"] = generic
    mods["pydantic_core"] = generic
    mods["tenacity"] = (
        "def retry(*a, **k):\n    return lambda f: f\n"
        "def stop_after_attempt(*a, **k):\n    return None\n"
        "def wait_fixed(*a, **k):\n    return None\n"
        "def retry_if_exception_type(*a, **k):\n    return None\n"
    )
    mods["tree_sitter"] = "class Node:\n    pass\nclass Parser:\n    pass\nclass Language:\n    pass\n"
    mods["openai"] = "class AsyncOpenAI:\n    def __init__(self, *a, **k):\n        pass\n"
    # ship the normalised prompt module under every alias the loader may try
    mods[f"workspace.GSM8K.workflows.{round_name}.prompt"] = prompt_module
    mods["prompt"] = prompt_module
    return mods


def main() -> int:
    run_id = "l3r1-replay-" + uuid.uuid4().hex[:8]
    src_path = LIVE / "real_model_responses.json"
    if not src_path.exists():
        print("MISSING real_model_responses.json")
        return 2

    # ---- Task A: build bundle (graph bytes untouched) ----
    try:
        bundle = load_bundle_from_live_responses(src_path)
    except (PromptContractError, BundleValidationError) as e:
        (OUT / "candidate_validation.json").write_text(json.dumps({
            "run_id": run_id, "status": "BUNDLE_REJECTED", "error": str(e),
        }, indent=2), encoding="utf-8")
        print("BUNDLE_REJECTED", e)
        return 1

    manifest = bundle.manifest()
    (OUT / "candidate_bundle_manifest.json").write_text(
        json.dumps({"run_id": run_id, **manifest}, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    evidence: Dict[str, Any] = {
        "run_id": run_id,
        "evidence_class": "OFFLINE_REPLAY (Mock IPC, no real DeepSeek)",
        "ORIGINAL_GRAPH_SHA": bundle.graph_sha256,
        "PROMPT_RAW_SHA": bundle.prompt_raw_sha256,
        "PROMPT_MODULE_SHA": bundle.prompt_module_sha256,
        "BUNDLE_SHA": bundle.bundle_sha256,
        "XML_VALID": True,  # came from live parse; graph/prompt present
        "GRAPH_SYNTAX_VALID": bundle.graph_compile_ok,
        "PROMPT_CONTRACT_VALID": bundle.prompt_compile_ok,
        "BUNDLE_LOAD_VALID": False,
        "WORKFLOW_EXECUTABLE": False,
        "IPC_REACHED": False,
        "TASK_CORRECT": False,
        "graph_rewritten": False,
    }

    # ---- pre-execution load check ----
    try:
        compile(bundle.graph_src, "<graph>", "exec")
        compile(bundle.prompt_module, "<prompt>", "exec")
        evidence["BUNDLE_LOAD_VALID"] = True
    except SyntaxError as e:
        evidence["load_error"] = str(e)
        (OUT / "replay_execution.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        return 1

    # ---- Task C: Docker + Mock IPC execution ----
    task = load_offline_tasks("search")[0]
    extras = _collect_modules(bundle.prompt_module, "round_2")
    child = run_workflow_code_isolated(
        bundle.graph_src,
        problem=task.question,
        task_id=task.task_id,
        gold_answer=None,
        llm=MockIPC(),
        timeout=30,
        extra_modules=extras,
    )
    out = child.get("stdout") or ""
    model_text = out
    container_keys = None
    try:
        payload = json.loads(out[out.find("{"):])
        model_text = payload.get("out", out)
        container_keys = payload.get("task_keys")
    except Exception:
        pass

    evidence["DOCKER_EXECUTION_STATUS"] = "PASS" if child.get("ok") else "FAIL"
    evidence["docker_returncode"] = child.get("returncode")
    evidence["docker_stderr_tail"] = (child.get("stderr") or "")[-400:]
    evidence["WORKFLOW_EXECUTABLE"] = bool(child.get("ok"))
    evidence["IPC_PROCESSED"] = len(child.get("ipc_processed") or [])
    evidence["IPC_REACHED"] = evidence["IPC_PROCESSED"] > 0
    evidence["container_task_keys"] = container_keys
    evidence["gold_in_container"] = False

    sc = evaluate_workflow_output(task, model_text)
    evidence["raw_output"] = str(model_text)[:300]
    evidence["predicted_answer"] = sc.get("predicted")
    evidence["gold_answer_host_only"] = sc.get("gold")
    evidence["TASK_CORRECT"] = bool(sc.get("correct"))
    evidence["scoring_reason"] = sc.get("reason")
    evidence["graph_sha_after_exec_note"] = "graph source bytes were executed as saved; not rewritten"

    (OUT / "replay_execution.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- negative cases (Task C requirement) ----
    negatives = {}
    # missing prompt
    try:
        build_bundle(graph_src=bundle.graph_src, prompt_field="")
        negatives["missing_prompt"] = "FAIL_NOT_REJECTED"
    except PromptContractError as e:
        negatives["missing_prompt"] = f"REJECTED:{e}"
    # invalid python graph
    try:
        build_bundle(graph_src="class Workflow:\n    def broken(:\n", prompt_field="x")
        negatives["invalid_python"] = "FAIL_NOT_REJECTED"
    except BundleValidationError as e:
        negatives["invalid_python"] = f"REJECTED:{e}"
    # missing Workflow class
    try:
        build_bundle(graph_src="def f(): return 1\n", prompt_field="x")
        negatives["missing_workflow"] = "FAIL_NOT_REJECTED"
    except BundleValidationError as e:
        negatives["missing_workflow"] = f"REJECTED:{e}"
    # wrong dependency -> child should fail closed
    bad_child = run_workflow_code_isolated(
        "import module_that_does_not_exist_xyz\n"
        "class Workflow:\n"
        "    def __init__(self, llm=None):\n        self.llm = llm\n"
        "    async def __call__(self, p):\n        return 'x'\n",
        problem=task.question, task_id="neg", gold_answer=None,
        llm=MockIPC(), timeout=20, extra_modules=extras,
    )
    negatives["wrong_dependency"] = "PASS_EXEC_FAILED" if not bad_child.get("ok") else "FAIL_UNEXPECTED_SUCCESS"
    negatives["wrong_dependency_stderr"] = (bad_child.get("stderr") or "")[-200:]

    (OUT / "replay_negative_tests.json").write_text(
        json.dumps({"run_id": run_id, "negatives": negatives}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps({
        "run_id": run_id,
        "DOCKER_EXECUTION_STATUS": evidence["DOCKER_EXECUTION_STATUS"],
        "IPC_PROCESSED": evidence["IPC_PROCESSED"],
        "BUNDLE_LOAD_VALID": evidence["BUNDLE_LOAD_VALID"],
        "PROMPT_CONTRACT_VALID": evidence["PROMPT_CONTRACT_VALID"],
        "TASK_CORRECT": evidence["TASK_CORRECT"],
        "GRAPH_SHA": bundle.graph_sha256[:16],
        "PROMPT_MODULE_SHA": bundle.prompt_module_sha256[:16],
        "BUNDLE_SHA": bundle.bundle_sha256[:16],
    }, indent=2))
    return 0 if evidence["WORKFLOW_EXECUTABLE"] and evidence["IPC_REACHED"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
