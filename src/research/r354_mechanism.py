"""R3.5.4 mechanism isolation: B / A / O arms.

Same feedback text for A and O. Only intended difference:
  A = append feedback suffix to non-empty base strategy
  O = replace base strategy with the same feedback text

B is a separately frozen non-empty baseline (NOT the empty-instruction Parent).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from src.research.r3_mutation_feedback import FailureRecord
from src.research.r35_f_local import build_feedback_diagnosis
from src.research.r4_workflow_program import (
    MutationError,
    WorkflowProgram,
    mutate_insert_instruction,
    program_provenance,
)

__all__ = [
    "PROTOCOL_ID",
    "BASE_STRATEGY_TEXT",
    "freeze_baseline_b",
    "build_append_child",
    "build_replace_child",
    "feedback_text_for_label",
]

PROTOCOL_ID = "MICRO-R3.5.4-MECHANISM-ISOLATION-v1"

# Frozen non-empty base strategy (separate protocol freeze; not empty Parent).
BASE_STRATEGY_TEXT = (
    "Solve the problem step by step. Identify the quantities, compute the result, "
    "and end with 'Answer: <num>'."
)

# Same text for A and O — identical feedback instruction content.
FEEDBACK_TEXT = {
    "ANSWER_MISMATCH": " Double-check the final calculation before answering.",
    "EXECUTION_ERROR": " Retry the failed step carefully.",
    "UNKNOWN_OR_PARSE": " End with the line: Answer: <number>",
}


def feedback_text_for_label(label: str) -> Optional[str]:
    return FEEDBACK_TEXT.get(label)


@dataclass
class FrozenBaseline:
    protocol_id: str
    base_text: str
    base_text_sha256: str
    program_id: str
    graph_sha256: str
    source: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def freeze_baseline_b(parent: WorkflowProgram) -> Dict[str, Any]:
    """Create frozen non-empty baseline B from (empty) Parent via one edit.

    Records text, hashes, and source. Does not rename Parent to B silently.
    """
    child = mutate_insert_instruction(parent, instruction=BASE_STRATEGY_TEXT)
    prov = program_provenance(child)
    fb = FrozenBaseline(
        protocol_id=PROTOCOL_ID,
        base_text=BASE_STRATEGY_TEXT,
        base_text_sha256=hashlib.sha256(BASE_STRATEGY_TEXT.encode("utf-8")).hexdigest(),
        program_id=child.program_id,
        graph_sha256=prov["graph_sha256"],
        source="derived_from_frozen_parent_single_instruction_set",
    )
    return {"program": child, "freeze": fb.to_dict(), "parent_program_id": parent.program_id}


def build_append_child(
    baseline: WorkflowProgram,
    diagnosis_label: str,
    *,
    feedback_id: str,
    source_task_ids: Sequence[str],
) -> Dict[str, Any]:
    """A: append feedback text after base strategy (base prefix preserved)."""
    fb_text = feedback_text_for_label(diagnosis_label)
    record = {
        "arm": "A",
        "operator": "APPEND_FEEDBACK_SUFFIX",
        "feedback_label": diagnosis_label,
        "feedback_id": feedback_id,
        "source_task_ids": list(source_task_ids),
        "parent_program_id": baseline.program_id,
        "parent_graph_sha256": program_provenance(baseline)["graph_sha256"],
        "gold_in_candidate_prompt": False,
    }
    if not fb_text:
        record.update({"status": "NO_USABLE_FEEDBACK", "reason": "NO_SUFFIX_FOR_LABEL"})
        return {"child": None, "record": record}
    new_instr = (baseline.instruction or "").rstrip() + fb_text
    if new_instr == (baseline.instruction or ""):
        record.update({"status": "NO_OP", "reason": "INSTRUCTION_UNCHANGED"})
        return {"child": None, "record": record}
    try:
        child = mutate_insert_instruction(baseline, instruction=new_instr)
    except MutationError as exc:
        record.update({"status": "FAILED", "reason": str(exc.args[0]) if exc.args else type(exc).__name__})
        return {"child": None, "record": record}
    prefix_ok = (baseline.instruction or "")[:20] in (child.instruction or "")
    record.update({
        "status": "SUCCESS",
        "child_program_id": child.program_id,
        "child_graph_sha256": program_provenance(child)["graph_sha256"],
        "generation": child.generation,
        "instruction_before": baseline.instruction,
        "instruction_after": child.instruction,
        "base_prefix_preserved": prefix_ok,
        "feedback_text_used": fb_text,
    })
    return {"child": child, "record": record}


def build_replace_child(
    baseline: WorkflowProgram,
    diagnosis_label: str,
    *,
    feedback_id: str,
    source_task_ids: Sequence[str],
) -> Dict[str, Any]:
    """O: replace base strategy with the SAME feedback text (not append)."""
    fb_text = feedback_text_for_label(diagnosis_label)
    record = {
        "arm": "O",
        "operator": "REPLACE_WITH_FEEDBACK_TEXT",
        "feedback_label": diagnosis_label,
        "feedback_id": feedback_id,
        "source_task_ids": list(source_task_ids),
        "parent_program_id": baseline.program_id,
        "parent_graph_sha256": program_provenance(baseline)["graph_sha256"],
        "gold_in_candidate_prompt": False,
    }
    if not fb_text:
        record.update({"status": "NO_USABLE_FEEDBACK", "reason": "NO_SUFFIX_FOR_LABEL"})
        return {"child": None, "record": record}
    new_instr = fb_text.strip()
    if new_instr == (baseline.instruction or ""):
        record.update({"status": "NO_OP", "reason": "INSTRUCTION_UNCHANGED"})
        return {"child": None, "record": record}
    try:
        child = mutate_insert_instruction(baseline, instruction=new_instr)
    except MutationError as exc:
        record.update({"status": "FAILED", "reason": str(exc.args[0]) if exc.args else type(exc).__name__})
        return {"child": None, "record": record}
    prefix_ok = (baseline.instruction or "")[:20] in (child.instruction or "")
    record.update({
        "status": "SUCCESS",
        "child_program_id": child.program_id,
        "child_graph_sha256": program_provenance(child)["graph_sha256"],
        "generation": child.generation,
        "instruction_before": baseline.instruction,
        "instruction_after": child.instruction,
        "base_prefix_preserved": prefix_ok,  # expected False for O
        "feedback_text_used": fb_text,
    })
    return {"child": child, "record": record}


def diagnosis_from_dev_failures(records: Sequence[FailureRecord]):
    """Only real dev failures; None if none."""
    fails = [r for r in records if not r.success]
    if not fails:
        return None
    return build_feedback_diagnosis(fails)
