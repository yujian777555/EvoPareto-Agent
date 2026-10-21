"""Docker/IPC evidence-boundary tests.

Layers:
  SIMULATED_LOCAL        — in-process HookLLM
  SIMULATED_DOCKER_IPC   — Docker + stub Custom
  PRODUCTION_ADAPTER     — Docker + real AFlow Custom/operator.py (still mock model)
  REAL_MODEL             — not used / not claimed

No DeepSeek. No real API key.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import compile_graph_source, load_frozen_parent
from src.runtime.workflow_ipc import run_workflow_code_isolated

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
AFLOW = ROOT / "external" / "AFlow"


class MockIPC:
    """Host-side mailbox double — NEVER hits network."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def _request(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._responses.pop(0) if self._responses else "Answer: 0"

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def _load_aflow_extras() -> dict:
    """Mirror R3: real AFlow sources + dependency stubs (no network)."""
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
    if AFLOW.exists():
        for base in (AFLOW / "workspace", AFLOW / "scripts", AFLOW / "benchmarks"):
            if not base.exists():
                continue
            for py in base.rglob("*.py"):
                if "__pycache__" in str(py):
                    continue
                rel = py.relative_to(AFLOW)
                dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
                try:
                    extras[dotted] = py.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass
    return extras


def test_production_custom_prompt_is_instruction_plus_input():
    """Contract check: production Custom concatenates instruction+input (no newline)."""
    src = (AFLOW / "workspace/GSM8K/workflows/template/operator.py").read_text(encoding="utf-8")
    assert "prompt = instruction + input" in src
    assert "call_with_format" in (AFLOW / "scripts/operators.py").read_text(encoding="utf-8")


@pytest.mark.skipif(not AFLOW.exists(), reason="AFlow sources not present")
def test_parent_with_production_aflow_adapter():
    """PRODUCTION_ADAPTER: real Custom module + mock model in Docker IPC."""
    parent = load_frozen_parent(FROZEN)
    graph = compile_graph_source(parent)
    extras = _load_aflow_extras()
    llm = MockIPC(["Answer: 42"])
    res = run_workflow_code_isolated(
        graph,
        problem="What is 6*7?",
        task_id="prod-parent-1",
        gold_answer=None,
        llm=llm,
        timeout=90,
        extra_modules=extras,
    )
    assert res.get("ok") is True, res
    assert "42" in str(res.get("answer_text"))
    # prompt construction: empty instruction + problem
    assert any("What is 6*7?" in c for c in llm.calls)


def test_evidence_layers_documented():
    text = Path(__file__).read_text(encoding="utf-8")
    for layer in ("SIMULATED_LOCAL", "SIMULATED_DOCKER_IPC", "PRODUCTION_ADAPTER", "REAL_MODEL"):
        assert layer in text
    # REAL_MODEL must not be presented as achieved
    assert "REAL_MODEL" in text and "not claimed" in text.lower() or "not used" in text.lower()
