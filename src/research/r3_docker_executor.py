"""R3.1 unified Docker/IPC candidate execution.

Runs compiled ``graph_source`` through production ``run_workflow_code_isolated``.
``executed_graph_source`` is evidence-based (Docker ok + structured answer or
explicit error), never a hardcoded True.

Zero real model API: callers inject a mock/real llm mailbox object only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.research.r4_workflow_program import (
    WorkflowProgram,
    compile_graph_source,
    program_provenance,
)
from src.runtime.workflow_ipc import run_workflow_code_isolated

__all__ = [
    "build_production_extras",
    "execute_candidate_docker",
    "evidence_executed_graph",
]


def build_production_extras() -> Dict[str, str]:
    """Dependency stubs + real AFlow sources (same pattern as production adapter tests)."""
    generic = (
        "class BaseModel:\n    def __init__(self, **kw):\n        pass\n"
        "def Field(default=None, **kw):\n    return default\n"
        "def create_model(name, **kw):\n    return type(name, (BaseModel,), {})\n"
        "def to_jsonable_python(x, **k):\n    return x\n"
        "def __getattr__(name):\n"
        "    if name.startswith('__') and name.endswith('__'):\n        raise AttributeError(name)\n"
        "    return type('_A', (), {'__init__': lambda self,*a,**k: None, '__call__': lambda self,*a,**k: self})()\n"
    )
    extras = {
        "pydantic": generic,
        "pydantic_core": generic,
        "typing_extensions": generic,
        "annotated_types": generic,
        "aiofiles": generic,
        "numpy": generic,
        "pandas": generic,
        "httpx": generic,
        "anyio": generic,
        "tqdm": generic,
        "tqdm.asyncio": "async def tqdm_asyncio(*a, **k):\n    pass\n",
        "regex": generic,
        "sympy": generic,
        "sympy.parsing": "",
        "sympy.parsing.latex": "def parse_latex(*a, **k):\n    return None\n",
        "sympy.parsing.sympy_parser": "def parse_expr(*a, **k):\n    return None\n",
        "pytz": generic,
        "tenacity": "def retry(*a, **k):\n    return lambda f: f\ndef stop_after_attempt(*a, **k):\n    return None\ndef wait_fixed(*a, **k):\n    return None\ndef retry_if_exception_type(*a, **k):\n    return None\n",
        "tree_sitter": "class Node:\n    pass\nclass Parser:\n    pass\nclass Language:\n    pass\n",
        "openai": "class AsyncOpenAI:\n    def __init__(self, *a, **k):\n        pass\nclass OpenAI(AsyncOpenAI):\n    pass\n",
        "yaml": "def safe_load(*a, **k):\n    return {}\n",
    }
    aflow = Path("external/AFlow")
    if aflow.exists():
        for base in (aflow / "workspace", aflow / "scripts", aflow / "benchmarks"):
            if not base.exists():
                continue
            for py in base.rglob("*.py"):
                if "__pycache__" in str(py):
                    continue
                rel = py.relative_to(aflow)
                dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
                try:
                    extras[dotted] = py.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    return extras


def evidence_executed_graph(result: Dict[str, Any]) -> bool:
    """Evidence-based flag: only True if container ran and produced structured output.

    Success requires:
      * no top-level error
      * docker_ok true (or container_created and not failed)
      * answer_text is not None
      * compiled graph was the artifact (caller supplies graph_sha256 match separately)
    """
    if result.get("error"):
        return False
    cleanup = result.get("docker_cleanup") or {}
    if cleanup.get("container_created") is False:
        return False
    if cleanup.get("error"):
        return False
    if not result.get("ok", False):
        return False
    if result.get("answer_text") is None:
        return False
    return True


def execute_candidate_docker(
    prog: WorkflowProgram,
    problem: str,
    *,
    llm: Any,
    task_id: str = "adhoc",
    timeout: int = 90,
    extra_modules: Optional[Dict[str, str]] = None,
    expect_graph_sha256: Optional[str] = None,
) -> Dict[str, Any]:
    """Unified production entry: compile graph_source and run in Docker/IPC.

    Associates program_id, parent_program_id, generation, graph SHA with the
    execution record. ``executed_graph_source`` is derived from run evidence.
    """
    prov = program_provenance(prog)
    try:
        graph_src = compile_graph_source(prog)
        compile_error = None
    except Exception as exc:
        return {
            "ok": False,
            "executed_graph_source": False,
            "error": f"GRAPH_COMPILE:{type(exc).__name__}:{exc}",
            "program_id": prog.program_id,
            "parent_program_id": prog.parent_program_id,
            "generation": prog.generation,
            "graph_sha256": prov["graph_sha256"],
            "answer_text": None,
            "n_llm_calls": 0,
            "evidence_class": "SIMULATED_DOCKER_IPC",
        }

    extras = extra_modules if extra_modules is not None else build_production_extras()
    res = run_workflow_code_isolated(
        graph_src,
        problem=problem,
        task_id=task_id,
        gold_answer=None,
        llm=llm,
        timeout=timeout,
        extra_modules=extras,
    )
    res = dict(res)
    res["program_id"] = prog.program_id
    res["parent_program_id"] = prog.parent_program_id
    res["generation"] = prog.generation
    res["operator_history"] = list(prog.operator_history)
    res["graph_sha256"] = prov["graph_sha256"]
    res["graph_sha256_expected"] = expect_graph_sha256 or prov["graph_sha256"]
    res["graph_sha256_match"] = (res["graph_sha256"] == res["graph_sha256_expected"])
    res["n_llm_calls"] = len(res.get("ipc_processed") or []) or (1 if res.get("answer_text") is not None else 0)
    res["executed_graph_source"] = evidence_executed_graph(res)
    res["evidence_class"] = "SIMULATED_DOCKER_IPC"
    res["production_entry"] = "run_workflow_code_isolated"
    return res
