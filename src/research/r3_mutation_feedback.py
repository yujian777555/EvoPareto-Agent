"""R3 unified candidate execution + seeded random mutation + feedback mutation.

Offline-first. No network. Real-model execution requires an injected chat
callable; Mock LLM used in tests and offline validation.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.research.r4_workflow_program import (
    FailedCandidate,
    MutationError,
    WorkflowProgram,
    compile_graph_source,
    execute_program_locally,
    load_frozen_parent,
    mutate_add_sampling,
    mutate_insert_instruction,
    mutate_single_edit,
    program_provenance,
)

__all__ = [
    "FailureRecord",
    "FeedbackSummary",
    "MUTATION_OPERATOR_NAMES",
    "apply_random_mutation",
    "select_feedback_operator",
    "build_feedback_child",
    "execute_candidate",
    "execute_candidates_paired",
    "hash_program",
]


# ---------------------------------------------------------------------------
# Unified execution entry — ALWAYS runs graph_source (fixes R2 fidelity gap)
# ---------------------------------------------------------------------------

def execute_candidate(
    prog: WorkflowProgram,
    problem: str,
    *,
    llm_hook: Callable[..., Any],
    timeout_s: float = 30.0,
) -> Dict[str, Any]:
    """Execute candidate via compiled graph_source (NOT instruction-only).

    Returns ok/answer_text/n_llm_calls/request_log/provenance.
    Raises nothing on model errors — returns ok=False with error.
    """
    install_aflow_mocks()
    import sys as _sys

    _al = _sys.modules.get("scripts.async_llm")
    if _al is not None:
        _al._live_hook = llm_hook
    prov = program_provenance(prog)
    res = execute_program_locally(prog, problem, llm_hook=llm_hook, timeout_s=timeout_s)
    res = dict(res)
    res["program_id"] = prog.program_id
    res["graph_sha256"] = prov["graph_sha256"]
    res["parent_program_id"] = prog.parent_program_id
    res["generation"] = prog.generation
    res["executed_graph_source"] = True
    return res


def execute_candidates_paired(
    candidates: Sequence[Tuple[str, WorkflowProgram]],
    problems: Sequence[Tuple[str, str]],
    *,
    llm_factory: Callable[[str, str], Callable[..., Any]],
) -> Dict[str, Any]:
    """Run every candidate on every problem through the unified entry.

    ``llm_factory(cand_id, task_id)`` returns the mock/real hook.
    """
    rows = []
    for cand_id, prog in candidates:
        for task_id, problem in problems:
            hook = llm_factory(cand_id, task_id)
            r = execute_candidate(prog, problem, llm_hook=hook)
            rows.append({"cand_id": cand_id, "task_id": task_id, **{k: r.get(k) for k in (
                "ok", "answer_text", "n_llm_calls", "error", "graph_sha256", "executed_graph_source",
            )}})
    return {"rows": rows}


def hash_program(prog: WorkflowProgram) -> str:
    return program_provenance(prog)["graph_sha256"]


# ---------------------------------------------------------------------------
# Failure / feedback
# ---------------------------------------------------------------------------

@dataclass
class FailureRecord:
    task_id: str
    parent_program_id: str
    parent_graph_sha256: str
    success: bool
    error_category: str  # ANSWER_MISMATCH | EXECUTION_ERROR | PARSE_ERROR | NO_FEEDBACK
    predicted: Optional[str] = None
    gold: Optional[str] = None
    diagnostic: Optional[str] = None
    # gold must never enter solve prompts; kept only for host-side diagnosis record
    diagnosis_uses_gold: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeedbackSummary:
    records: List[FailureRecord]
    coarse_label: str  # e.g. ANSWER_MISMATCH
    rationale: str
    eligible: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "coarse_label": self.coarse_label,
            "rationale": self.rationale,
            "eligible": self.eligible,
            "n_records": len(self.records),
            "records": [r.to_dict() for r in self.records],
        }


def summarize_feedback(records: Sequence[FailureRecord]) -> FeedbackSummary:
    """Coarse feedback only. Never invents fine-grained error causes."""
    fails = [r for r in records if not r.success]
    if not fails:
        return FeedbackSummary(list(records), "NO_FAILURE", "all recorded tasks succeeded", False)
    # Only label what is verifiable: predicted != gold, or execution error
    cats = set()
    for r in fails:
        if r.error_category == "EXECUTION_ERROR":
            cats.add("EXECUTION_ERROR")
        elif r.predicted is not None and r.gold is not None and r.predicted != r.gold:
            cats.add("ANSWER_MISMATCH")
        else:
            cats.add("UNKNOWN_OR_PARSE")
    if len(cats) == 1:
        label = next(iter(cats))
        rationale = "single verifiable coarse category from failure records"
    else:
        label = "ANSWER_MISMATCH"
        rationale = "mixed failure categories; defaulting to coarse ANSWER_MISMATCH (no fine-grained attribution claimed)"
    return FeedbackSummary(list(records), label, rationale, eligible=True)


# ---------------------------------------------------------------------------
# Seeded random mutation (operator set)
# ---------------------------------------------------------------------------

MUTATION_OPERATOR_NAMES = (
    "OP_INSTRUCTION_STYLE",
    "OP_REASONING_ORG",
    "OP_ARITH_RECHECK",
    "OP_ERROR_RECOVERY",
    "OP_OUTPUT_CONSTRAINT",
)

_OP_PRESETS = {
    "OP_INSTRUCTION_STYLE": [
        "Answer briefly and directly. End with 'Answer: <num>'.",
        "Write a compact one-line derivation. End with 'Answer: <num>'.",
    ],
    "OP_REASONING_ORG": [
        "List given quantities, then compute. End with 'Answer: <num>'.",
        "Do the computation in numbered steps. End with 'Answer: <num>'.",
    ],
    "OP_ARITH_RECHECK": [
        "Compute, then re-add the key numbers once. End with 'Answer: <num>'.",
        "Solve, then verify the final arithmetic. End with 'Answer: <num>'.",
    ],
    "OP_ERROR_RECOVERY": [
        "If a step looks wrong, redo that step. End with 'Answer: <num>'.",
        "Self-correct any intermediate mistake. End with 'Answer: <num>'.",
    ],
    "OP_OUTPUT_CONSTRAINT": [
        "Output only the final integer after the token Answer:.",
        "No prose after the final Answer: number.",
    ],
}


def apply_random_mutation(
    parent: WorkflowProgram,
    *,
    seed: int,
    slot: int = 0,
    operator: Optional[str] = None,
) -> Tuple[Optional[WorkflowProgram], Dict[str, Any]]:
    """Seeded random mutation. Returns (child|None, record).

    Rejects empty / no-op mutations (child=None, record status=FAILED).
    """
    rng = random.Random((seed << 8) ^ slot)
    op = operator or rng.choice(MUTATION_OPERATOR_NAMES)
    if op not in _OP_PRESETS:
        return None, {
            "operator": op,
            "status": "FAILED",
            "reason": "UNKNOWN_OPERATOR",
            "parent_program_id": parent.program_id,
            "parent_graph_sha256": hash_program(parent),
            "seed": seed,
            "slot": slot,
        }
    params = {"instruction_pool_index": rng.randrange(len(_OP_PRESETS[op]))}
    instr = _OP_PRESETS[op][params["instruction_pool_index"]]
    if instr == parent.instruction:
        params["instruction_pool_index"] = (params["instruction_pool_index"] + 1) % len(_OP_PRESETS[op])
        instr = _OP_PRESETS[op][params["instruction_pool_index"]]
    rec = {
        "operator": op,
        "params": params,
        "parent_program_id": parent.program_id,
        "parent_graph_sha256": hash_program(parent),
        "seed": seed,
        "slot": slot,
    }
    try:
        child = mutate_insert_instruction(parent, instruction=instr)
    except MutationError as exc:
        rec.update({"status": "FAILED", "reason": str(exc.args[0]) if exc.args else type(exc).__name__})
        return None, rec
    rec.update({
        "status": "SUCCESS",
        "child_program_id": child.program_id,
        "child_graph_sha256": hash_program(child),
        "generation": child.generation,
        "operator_history": list(child.operator_history),
    })
    return child, rec


# ---------------------------------------------------------------------------
# Feedback-driven mutation policy
# ---------------------------------------------------------------------------

_FB_POLICY = {
    "ANSWER_MISMATCH": ["OP_ARITH_RECHECK", "OP_REASONING_ORG"],
    "EXECUTION_ERROR": ["OP_ERROR_RECOVERY", "OP_OUTPUT_CONSTRAINT"],
    "UNKNOWN_OR_PARSE": ["OP_OUTPUT_CONSTRAINT", "OP_INSTRUCTION_STYLE"],
    "NO_FAILURE": ["OP_INSTRUCTION_STYLE"],
    "NO_FEEDBACK": [],
}


def select_feedback_operator(summary: FeedbackSummary) -> Optional[str]:
    """Pick operator from coarse feedback. None if no usable feedback."""
    if not summary.eligible:
        return None
    pool = _FB_POLICY.get(summary.coarse_label, ["OP_INSTRUCTION_STYLE"])
    if not pool:
        return None
    # deterministic: first in policy list
    return pool[0]


def build_feedback_child(
    parent: WorkflowProgram,
    summary: FeedbackSummary,
    *,
    seed: int,
    slot: int = 0,
) -> Tuple[Optional[WorkflowProgram], Dict[str, Any]]:
    """Feedback-driven child. Fails explicitly when feedback is insufficient."""
    op = select_feedback_operator(summary)
    rec = {
        "parent_program_id": parent.program_id,
        "feedback_label": summary.coarse_label,
        "feedback_rationale": summary.rationale,
        "selected_operator": op,
        "seed": seed,
        "slot": slot,
    }
    if op is None:
        rec.update({"status": "FAILED", "reason": "NO_USABLE_FEEDBACK"})
        return None, rec
    child, mut = apply_random_mutation(parent, seed=seed, slot=slot, operator=op)
    rec.update(mut)
    rec["status"] = mut.get("status", "FAILED")
    rec["selection_reason"] = f"policy[{summary.coarse_label}] -> {op}"
    return child, rec

# ---------------------------------------------------------------------------
# Mock AFlow stubs so frozen Parent graph_source can execute offline
# ---------------------------------------------------------------------------

def install_aflow_mocks() -> None:
    """Install minimal stubs for AFlow imports used by frozen parent_graph.py."""
    import sys
    import types

    def ensure(name, mod=None):
        if name in sys.modules:
            return sys.modules[name]
        m = mod or types.ModuleType(name)
        sys.modules[name] = m
        return m

    op_mod = ensure("workspace.GSM8K.workflows.template.operator")

    class Custom:
        def __init__(self, llm):
            self.llm = llm

        async def __call__(self, input=None, instruction="", **kw):
            prompt = (str(instruction) + "\n" + str(input)) if instruction else str(input)
            out = self.llm._request(prompt) if hasattr(self.llm, "_request") else self.llm(prompt)
            if hasattr(out, "__await__"):
                out = await out
            return {"response": out}

    op_mod.Custom = Custom
    ensure("workspace")
    ensure("workspace.GSM8K")
    ensure("workspace.GSM8K.workflows")
    ensure("workspace.GSM8K.workflows.template")
    ensure("workspace.GSM8K.workflows.round_1")
    ensure("workspace.GSM8K.workflows.round_1.prompt")
    sys.modules["workspace.GSM8K.workflows.round_1.prompt"].INSTRUCTION = ""
    ensure("scripts")
    al = ensure("scripts.async_llm")

    # create_llm_instance must return an object callable by AFlow Custom.
    # execute_program_locally replaces obj.llm when None; Custom holds its own
    # llm from construction, so we return a passthrough that reads the live hook.
    class _LiveLLM:
        def _request(self, prompt):
            fn = getattr(al, "_live_hook", None)
            if fn is None:
                raise RuntimeError("NO_LIVE_HOOK")
            return fn(prompt)

        def __call__(self, prompt):
            return self._request(prompt)

        def get_usage_summary(self):
            return {"total_cost": 0.0}

    al.create_llm_instance = lambda *a, **k: _LiveLLM()
    al._live_hook = None
    ev = ensure("scripts.evaluator")

    class DatasetType:
        pass

    ev.DatasetType = DatasetType
    ensure("prompt").INSTRUCTION = ""

