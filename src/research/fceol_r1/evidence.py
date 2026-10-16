"""Failure evidence (policy-visible) — built from execution events only."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

UNKNOWN = "UNKNOWN"
VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
RECOVERY_FAILURE = "RECOVERY_FAILURE"
TOOL_SELECTION_FAILURE = "TOOL_SELECTION_FAILURE"
CONTEXT_FAILURE = "CONTEXT_FAILURE"
PLANNING_FAILURE = "PLANNING_FAILURE"

# symptom -> candidate categories (ambiguous)
_SYM_MAP = {
    "wrong_output_submitted": (VERIFICATION_FAILURE, PLANNING_FAILURE),
    "no_verification_performed": (VERIFICATION_FAILURE, PLANNING_FAILURE),
    "partial_solution": (VERIFICATION_FAILURE, PLANNING_FAILURE),
    "repair_without_improvement": (RECOVERY_FAILURE, VERIFICATION_FAILURE),
    "tool_misuse_detected": (TOOL_SELECTION_FAILURE, PLANNING_FAILURE),
    "constraint_lost": (CONTEXT_FAILURE, PLANNING_FAILURE),
    "clean_run": (UNKNOWN,),
}


@dataclass
class Evidence:
    task_id: str
    symptoms: List[str] = field(default_factory=list)
    diagnosis: str = UNKNOWN
    confidence: float = 0.0
    context_key: str = "ctx:UNKNOWN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "symptoms": list(self.symptoms),
            "diagnosis": self.diagnosis,
            "confidence": self.confidence,
            "context_key": self.context_key,
        }


def diagnose_from_symptoms(symptoms: List[str]) -> tuple:
    cats = []
    for s in symptoms:
        cats.extend(_SYM_MAP.get(s, (UNKNOWN,)))
    from collections import Counter

    if not cats:
        return UNKNOWN, 0.2
    c = Counter(cats)
    top, n = c.most_common(1)[0]
    if top == UNKNOWN:
        return UNKNOWN, 0.2
    ambig = 1.0 - n / len(cats)
    conf = max(0.25, 0.85 - 0.35 * ambig)
    return top, conf


def build_evidence(
    *,
    task_id: str,
    symptoms: List[str],
    mode: str = "TRUE_EVIDENCE",
    wrong_category: str = UNKNOWN,
    seed: int = 0,
) -> Evidence:
    """mode ∈ {TRUE_EVIDENCE, SHUFFLED_EVIDENCE, UNKNOWN_ONLY, WRONG_DIAGNOSIS}."""
    cat, conf = diagnose_from_symptoms(symptoms)
    if mode == "UNKNOWN_ONLY":
        return Evidence(task_id, list(symptoms), UNKNOWN, 0.1, "ctx:UNKNOWN")
    if mode == "WRONG_DIAGNOSIS":
        cat2 = wrong_category if wrong_category != UNKNOWN else PLANNING_FAILURE
        return Evidence(task_id, list(symptoms), cat2, 0.8, f"ctx:{cat2}:hi")
    if mode == "SHUFFLED_EVIDENCE":
        # deterministic permutation of category labels — seed stable
        import random

        pool = [VERIFICATION_FAILURE, RECOVERY_FAILURE, TOOL_SELECTION_FAILURE, CONTEXT_FAILURE, PLANNING_FAILURE]
        rng = random.Random((seed * 7919 + hash(task_id) % 10007) & 0xFFFFFFFF)
        # NOTE: use deterministic string hash to avoid PYTHONHASHSEED issues
        h = 0
        for ch in task_id:
            h = (h * 131 + ord(ch)) & 0xFFFFFFFF
        rng = random.Random((seed * 7919 + h) % (2**32))
        cat2 = pool[rng.randrange(len(pool))]
        return Evidence(task_id, list(symptoms), cat2, 0.7, f"ctx:{cat2}:md")
    # TRUE
    if conf < 0.35:
        return Evidence(task_id, list(symptoms), UNKNOWN, conf, "ctx:UNKNOWN")
    level = "hi" if conf >= 0.7 else "md"
    return Evidence(task_id, list(symptoms), cat, conf, f"ctx:{cat}:{level}")
