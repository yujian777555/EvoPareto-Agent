"""Failure evidence representation (Stage 2.0).

Separates symptoms / hypotheses / evidence / uncertainty. Never equates
"task failed" with a specific mechanism. UNKNOWN is first-class.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Observable failure mechanisms (closed vocabulary)
PLANNING_FAILURE = "PLANNING_FAILURE"
TOOL_SELECTION_FAILURE = "TOOL_SELECTION_FAILURE"
VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
RECOVERY_FAILURE = "RECOVERY_FAILURE"
CONTEXT_FAILURE = "CONTEXT_FAILURE"
OUTPUT_VALIDITY_FAILURE = "OUTPUT_VALIDITY_FAILURE"
UNKNOWN = "UNKNOWN"

FAILURE_CATEGORIES = (
    PLANNING_FAILURE,
    TOOL_SELECTION_FAILURE,
    VERIFICATION_FAILURE,
    RECOVERY_FAILURE,
    CONTEXT_FAILURE,
    OUTPUT_VALIDITY_FAILURE,
    UNKNOWN,
)


@dataclass
class FailureEvidence:
    task_id: str
    genome_id: str
    failure_category: str = UNKNOWN
    observed_symptoms: List[str] = field(default_factory=list)
    supporting_trace_ids: List[str] = field(default_factory=list)
    diagnostic_confidence: float = 0.0
    uncertainty: float = 1.0
    unknown_flag: bool = True

    def __post_init__(self) -> None:
        if self.failure_category not in FAILURE_CATEGORIES:
            self.failure_category = UNKNOWN
            self.unknown_flag = True
        if self.failure_category == UNKNOWN:
            self.unknown_flag = True
        # confidence in [0,1]; uncertainty complements it
        self.diagnostic_confidence = float(min(1.0, max(0.0, self.diagnostic_confidence)))
        self.uncertainty = float(min(1.0, max(0.0, self.uncertainty)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "genome_id": self.genome_id,
            "failure_category": self.failure_category,
            "observed_symptoms": list(self.observed_symptoms),
            "supporting_trace_ids": list(self.supporting_trace_ids),
            "diagnostic_confidence": self.diagnostic_confidence,
            "uncertainty": self.uncertainty,
            "unknown_flag": self.unknown_flag,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "FailureEvidence":
        return cls(
            task_id=str(d.get("task_id", "")),
            genome_id=str(d.get("genome_id", "")),
            failure_category=str(d.get("failure_category", UNKNOWN)),
            observed_symptoms=list(d.get("observed_symptoms") or []),
            supporting_trace_ids=list(d.get("supporting_trace_ids") or []),
            diagnostic_confidence=float(d.get("diagnostic_confidence", 0.0)),
            uncertainty=float(d.get("uncertainty", 1.0)),
            unknown_flag=bool(d.get("unknown_flag", True)),
        )

    def hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def context_key(self, *, bucket: bool = True) -> str:
        """Feature key for conditioning. Low-confidence evidence → UNKNOWN key.

        This is what the operator policy may see. Ground-truth fault type is
        NEVER part of this key.
        """
        if self.unknown_flag or self.diagnostic_confidence < 0.35:
            return "ctx:UNKNOWN"
        conf = "hi" if self.diagnostic_confidence >= 0.7 else "md"
        return f"ctx:{self.failure_category}:{conf}"


def evidence_from_trace(
    *,
    task_id: str,
    genome_id: str,
    symptoms: List[str],
    trace_ids: List[str],
    diagnosed_category: str = UNKNOWN,
    confidence: float = 0.0,
) -> FailureEvidence:
    """Build evidence from *observable* symptoms. Diagnosis may be UNKNOWN.

    Rule: low/no confidence cannot assert a specific category.
    """
    conf = float(confidence)
    if diagnosed_category not in FAILURE_CATEGORIES or conf < 0.35:
        return FailureEvidence(
            task_id=task_id,
            genome_id=genome_id,
            failure_category=UNKNOWN,
            observed_symptoms=list(symptoms),
            supporting_trace_ids=list(trace_ids),
            diagnostic_confidence=conf,
            uncertainty=1.0 - conf,
            unknown_flag=True,
        )
    return FailureEvidence(
        task_id=task_id,
        genome_id=genome_id,
        failure_category=diagnosed_category,
        observed_symptoms=list(symptoms),
        supporting_trace_ids=list(trace_ids),
        diagnostic_confidence=conf,
        uncertainty=1.0 - conf,
        unknown_flag=False,
    )
