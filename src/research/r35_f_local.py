"""R3.5 F_LOCAL: conservative local feedback mutation.

Appends a short evidence-tagged suffix to the parent instruction instead of
replacing the whole solve prompt (R3.4 defect: OP_ARITH_RECHECK overwrote
the working strategy and degraded accuracy).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Sequence

from src.research.r3_mutation_feedback import FailureRecord, summarize_feedback
from src.research.r4_workflow_program import (
    MutationError,
    WorkflowProgram,
    mutate_insert_instruction,
    program_provenance,
)

__all__ = [
    "FeedbackDiagnosis",
    "build_feedback_diagnosis",
    "apply_f_local",
    "F_LOCAL_SUFFIXES",
    "MUTATION_DIFF_NOTE",
]

# Local suffixes — never contain gold answers.
F_LOCAL_SUFFIXES = {
    "ANSWER_MISMATCH": [
        " Double-check the final calculation before answering.",
        " Re-read the last step and confirm the result.",
    ],
    "EXECUTION_ERROR": [
        " Retry the failed step carefully.",
    ],
    "UNKNOWN_OR_PARSE": [
        " End with the line: Answer: <number>",
    ],
    "NO_FAILURE": [],
}

MUTATION_DIFF_NOTE = "append-only instruction suffix; original solve logic retained"


@dataclass
class FeedbackDiagnosis:
    feedback_id: str
    coarse_label: str
    error_evidence: str
    possible_cause_hypothesis: str
    suggested_change: str
    source_task_ids: List[str]
    evidence_source: str
    gold_in_candidate_prompt: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_feedback_diagnosis(records: Sequence[FailureRecord]) -> Optional[FeedbackDiagnosis]:
    """Structured diagnosis from real failures only.

    Possible-cause is explicitly a HYPOTHESIS (coarse). Gold is recorded only
    as host-side evidence and never enters candidate prompts.
    """
    summary = summarize_feedback(list(records))
    if not summary.eligible:
        return None
    fails = [r for r in records if not r.success]
    if not fails:
        return None
    label = summary.coarse_label
    src_ids = [r.task_id for r in fails]
    fid = hashlib.sha256(("|".join(src_ids) + "|" + label).encode()).hexdigest()[:16]
    hypo = {
        "ANSWER_MISMATCH": "final numeric mismatch (cause NOT fine-attributed; arithmetic vs reasoning unknown)",
        "EXECUTION_ERROR": "execution/harness failure",
        "UNKNOWN_OR_PARSE": "unparseable model output",
    }.get(label, "unknown")
    change = {
        "ANSWER_MISMATCH": "append local verification suffix; do not rewrite full strategy",
        "EXECUTION_ERROR": "append retry hint only",
        "UNKNOWN_OR_PARSE": "tighten output format line only",
    }.get(label, "no change")
    return FeedbackDiagnosis(
        feedback_id=fid,
        coarse_label=label,
        error_evidence=f"{len(fails)} FailureRecord(s) with success=False",
        possible_cause_hypothesis=hypo,
        suggested_change=change,
        source_task_ids=src_ids,
        evidence_source="failure_archive / host-side scoring",
        gold_in_candidate_prompt=False,
    )


def apply_f_local(
    parent: WorkflowProgram,
    diagnosis: FeedbackDiagnosis,
    *,
    suffix_index: int = 0,
) -> Dict[str, Any]:
    """Local append mutation. Returns record with child or NO_OP / NO_USABLE_FEEDBACK."""
    record = {
        "operator": "F_LOCAL_APPEND_SUFFIX",
        "feedback_id": diagnosis.feedback_id,
        "feedback_label": diagnosis.coarse_label,
        "parent_program_id": parent.program_id,
        "parent_graph_sha256": program_provenance(parent)["graph_sha256"],
        "diff_note": MUTATION_DIFF_NOTE,
        "suffix_index": suffix_index,
        "gold_in_candidate_prompt": False,
    }
    pool = F_LOCAL_SUFFIXES.get(diagnosis.coarse_label, [])
    if not pool:
        record.update({"status": "NO_USABLE_FEEDBACK", "reason": "NO_SUFFIX_FOR_LABEL"})
        return {"child": None, "record": record}
    suffix = pool[suffix_index % len(pool)]
    base = parent.instruction or "Solve the problem."
    new_instr = (base.rstrip() + suffix).strip()
    if new_instr == (parent.instruction or ""):
        record.update({"status": "NO_OP", "reason": "INSTRUCTION_UNCHANGED"})
        return {"child": None, "record": record}
    try:
        child = mutate_insert_instruction(parent, instruction=new_instr)
    except MutationError as exc:
        record.update({"status": "FAILED", "reason": str(exc.args[0]) if exc.args else type(exc).__name__})
        return {"child": None, "record": record}
    # verify local-only: original prefix preserved
    prefix_ok = (parent.instruction or "Solve the problem.")[:10] in (child.instruction or "")
    record.update({
        "status": "SUCCESS",
        "child_program_id": child.program_id,
        "child_graph_sha256": program_provenance(child)["graph_sha256"],
        "generation": child.generation,
        "instruction_before": parent.instruction,
        "instruction_after": child.instruction,
        "local_prefix_preserved": prefix_ok,
    })
    return {"child": child, "record": record}

def generate_e2_from_winner(
    winner: WorkflowProgram,
    winner_failure_records: Sequence[FailureRecord],
    *,
    suffix_index: int = 0,
) -> Dict[str, Any]:
    """E2 must use the gen-1 winner's OWN failure records (not the parent's).

    If the winner has no real failures, returns NOT_GENERATED_NO_FAILURE and
    does not fabricate feedback. Records whose parent_program_id does not
    match the winner are rejected (FAILURE_RECORD_PARENT_MISMATCH).
    """
    record_base = {
        "operator": "E2_LOCAL_FROM_WINNER",
        "parent_program_id": winner.program_id,
        "parent_graph_sha256": program_provenance(winner)["graph_sha256"],
    }
    for r in winner_failure_records:
        if r.parent_program_id != winner.program_id:
            return {
                "child": None,
                "record": {
                    **record_base,
                    "status": "NOT_GENERATED_NO_FAILURE",
                    "reason": "FAILURE_RECORD_PARENT_MISMATCH",
                },
            }
    fails = [r for r in winner_failure_records if not r.success]
    if not fails:
        return {
            "child": None,
            "record": {
                **record_base,
                "status": "NOT_GENERATED_NO_FAILURE",
                "reason": "WINNER_NO_FAILURES",
                "feedback_id": None,
                "source_task_ids": [],
            },
        }
    diag = build_feedback_diagnosis(fails)
    if diag is None:
        return {
            "child": None,
            "record": {
                **record_base,
                "status": "NOT_GENERATED_NO_FAILURE",
                "reason": "NO_USABLE_FEEDBACK",
                "source_task_ids": [r.task_id for r in fails],
            },
        }
    out = apply_f_local(winner, diag, suffix_index=suffix_index)
    rec = dict(out["record"])
    rec["e2_feedback_id"] = diag.feedback_id
    rec["e2_source_task_ids"] = list(diag.source_task_ids)
    rec["e2_feedback_from"] = "winner_own_failure_records"
    child = out["child"]
    if child is not None:
        rec["parent_program_id"] = child.parent_program_id
        rec["generation"] = child.generation
        rec["status"] = "SUCCESS"
        # reject stacking an identical suffix with no effective change
        if child.instruction == winner.instruction:
            rec["status"] = "NO_OP"
            rec["reason"] = "IDENTICAL_INSTRUCTION_TO_WINNER"
            return {"child": None, "record": rec}
    return {"child": child, "record": rec}

