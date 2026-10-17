"""Candidate bundle contract: graph + prompt module normalisation (L3-R1 Task A).

The real Optimizer may return `<prompt>` as plain text. The official AFlow
runtime imports `prompt.py` as a Python module and the generated graph reads
the module-level name `INSTRUCTION`. The contract is therefore:

    prompt.py  ->  INSTRUCTION = <repr(prompt_text)>

The graph bytes are NEVER rewritten. Only the prompt module is serialised
deterministically, and both are hashed into a bundle manifest.
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


class PromptContractError(RuntimeError):
    pass


class BundleValidationError(RuntimeError):
    pass


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8", errors="replace"))


def normalize_prompt_module(prompt_field: str, return_kind: bool = False):
    """Deterministic safe serialisation: INSTRUCTION = repr(text).

    Accepts either raw plain text or an already-valid Python module that
    defines INSTRUCTION. Never mutates the text content.
    """
    if prompt_field is None:
        raise PromptContractError("PROMPT_FIELD_MISSING")
    text = prompt_field
    if not isinstance(text, str):
        raise PromptContractError("PROMPT_FIELD_NOT_STRING")
    stripped = text.strip()
    if not stripped:
        raise PromptContractError("PROMPT_FIELD_EMPTY")

    # Already a valid module defining INSTRUCTION? return original bytes verbatim.
    try:
        tree = ast.parse(text)
        names = {
            n.targets[0].id
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            and n.targets
            and isinstance(n.targets[0], ast.Name)
        }
        if "INSTRUCTION" in names:
            compile(text, "<prompt>", "exec")
            return (text, "PASSTHROUGH_PYTHON_MODULE") if return_kind else text
    except SyntaxError:
        pass

    # Plain text -> INSTRUCTION = repr(text)
    module = "INSTRUCTION = " + repr(text) + "\n"
    try:
        compile(module, "<prompt>", "exec")
    except SyntaxError as e:
        raise PromptContractError(f"SERIALISED_PROMPT_INVALID:{e.msg}") from e
    return (module, "SERIALISED_INSTRUCTION_REPR") if return_kind else module


@dataclass
class CandidateBundle:
    """Immutable view of one real-model candidate artefact set."""
    graph_src: str
    prompt_module: str
    prompt_raw_field: str
    modification: str
    graph_sha256: str
    prompt_raw_sha256: str
    prompt_module_sha256: str
    bundle_sha256: str
    graph_compile_ok: bool
    prompt_compile_ok: bool
    has_workflow_class: bool
    prompt_contract: str
    prompt_load_ok: bool
    instruction_binding_type: str

    def manifest(self) -> Dict[str, Any]:
        return asdict(self)


def build_bundle(
    *,
    graph_src: str,
    prompt_field: str,
    modification: str = "",
    extra_modules: Optional[Dict[str, str]] = None,
) -> CandidateBundle:
    """Validate + package a candidate. Fails loudly before any Docker run."""
    if not graph_src or not graph_src.strip():
        raise BundleValidationError("GRAPH_EMPTY")
    graph_bytes = graph_src.encode("utf-8")
    graph_sha = sha256_bytes(graph_bytes)

    # graph must compile and define Workflow — checked BEFORE execution
    try:
        compile(graph_src, "<graph>", "exec")
        graph_ok = True
    except SyntaxError as e:
        raise BundleValidationError(f"GRAPH_SYNTAX_INVALID:{e.msg}") from e
    try:
        tree = ast.parse(graph_src)
        has_wf = any(
            isinstance(n, ast.ClassDef) and n.name == "Workflow" for n in tree.body
        )
    except SyntaxError:
        has_wf = False
    if not has_wf:
        raise BundleValidationError("GRAPH_MISSING_WORKFLOW_CLASS")

    # prompt module (normalised, deterministic)
    prompt_module, prompt_kind = normalize_prompt_module(prompt_field, return_kind=True)
    try:
        compile(prompt_module, "<prompt>", "exec")
        prompt_ok = True
    except SyntaxError as e:
        raise PromptContractError(f"PROMPT_MODULE_INVALID:{e.msg}") from e
    # compile success != module load success: actually exec the module and
    # require the INSTRUCTION name to be a real module-level binding
    ns: Dict[str, Any] = {}
    try:
        exec(prompt_module, ns)
    except Exception as e:
        raise PromptContractError(f"PROMPT_MODULE_LOAD_FAIL:{type(e).__name__}:{e}") from e
    if "INSTRUCTION" not in ns:
        raise PromptContractError("PROMPT_MODULE_MISSING_INSTRUCTION_BINDING")
    if not isinstance(ns["INSTRUCTION"], str):
        raise PromptContractError("PROMPT_INSTRUCTION_NOT_STRING")

    prompt_raw_sha = sha256_text(prompt_field)
    prompt_mod_sha = sha256_text(prompt_module)
    bundle_sha = sha256_text(graph_sha + "|" + prompt_mod_sha)

    return CandidateBundle(
        graph_src=graph_src,
        prompt_module=prompt_module,
        prompt_raw_field=prompt_field,
        modification=modification,
        graph_sha256=graph_sha,
        prompt_raw_sha256=prompt_raw_sha,
        prompt_module_sha256=prompt_mod_sha,
        bundle_sha256=bundle_sha,
        graph_compile_ok=graph_ok,
        prompt_compile_ok=prompt_ok,
        has_workflow_class=has_wf,
        prompt_contract=prompt_kind,
        prompt_load_ok=True,
        instruction_binding_type=type(ns["INSTRUCTION"]).__name__,
    )


def load_bundle_from_live_responses(path: Path) -> CandidateBundle:
    """Rebuild a bundle from the saved real Level 3 model output (no API)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    opt = (data.get("stages") or {}).get("optimizer") or {}
    return build_bundle(
        graph_src=opt.get("graph") or "",
        prompt_field=opt.get("prompt") or "",
        modification=opt.get("modification") or "",
    )
