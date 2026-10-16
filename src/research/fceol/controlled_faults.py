"""Controlled fault-injection environment (Stage 2.0).

Ground-truth faults are stored SEPARATELY and never fed to the policy.
The policy only sees FailureEvidence built from observable symptoms.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.research.fceol.failure_evidence import (
    CONTEXT_FAILURE,
    PLANNING_FAILURE,
    RECOVERY_FAILURE,
    TOOL_SELECTION_FAILURE,
    UNKNOWN,
    VERIFICATION_FAILURE,
    FailureEvidence,
    evidence_from_trace,
)
from src.research.fceol.workflow_genome import WorkflowGenome

# ground-truth fault types (evaluation only)
FAULT_MISSING_VERIFY = "FAULT_MISSING_VERIFY"
FAULT_WRONG_RECOVERY = "FAULT_WRONG_RECOVERY"
FAULT_TOOL_ROUTING = "FAULT_TOOL_ROUTING"
FAULT_CONTEXT_TRUNCATION = "FAULT_CONTEXT_TRUNCATION"
FAULT_PLAN_GAP = "FAULT_PLAN_GAP"

FAULT_TYPES = (
    FAULT_MISSING_VERIFY,
    FAULT_WRONG_RECOVERY,
    FAULT_TOOL_ROUTING,
    FAULT_CONTEXT_TRUNCATION,
    FAULT_PLAN_GAP,
)

# symptom -> candidate mechanisms (non-injective on purpose)
_SYMPTOM_MAP = {
    "wrong_output_passed": (VERIFICATION_FAILURE, PLANNING_FAILURE),
    "infinite_repair_loop": (RECOVERY_FAILURE, PLANNING_FAILURE),
    "tool_misuse": (TOOL_SELECTION_FAILURE, PLANNING_FAILURE),
    "lost_context": (CONTEXT_FAILURE, VERIFICATION_FAILURE),
    "incomplete_plan": (PLANNING_FAILURE, TOOL_SELECTION_FAILURE),
    "no_output": (PLANNING_FAILURE, RECOVERY_FAILURE),
}


@dataclass
class TaskInstance:
    task_id: str
    fault_type: str  # ground truth — NEVER given to policy
    difficulty: float = 0.5
    family: str = "t"


@dataclass
class EvalResult:
    task_id: str
    genome_id: str
    success: bool
    reward: float
    symptoms: List[str]
    trace_id: str
    fault_type: str = ""  # eval-only


def observable_symptoms(fault: str, genome: WorkflowGenome, rng=None) -> List[str]:
    """Symptoms depend on BOTH fault and genome — not a lookup table."""
    e = genome.enabled_kinds()
    sym: List[str] = []
    if fault == FAULT_MISSING_VERIFY:
        if "VERIFY" not in e:
            sym.append("wrong_output_passed")
        else:
            sym.append("late_verification")  # present but weak
    elif fault == FAULT_WRONG_RECOVERY:
        if "REPAIR" not in e or genome.max_repairs <= 0:
            sym.append("infinite_repair_loop")
        else:
            sym.append("repair_ineffective")
    elif fault == FAULT_TOOL_ROUTING:
        if genome.route_policy == "direct":
            sym.append("tool_misuse")
        else:
            sym.append("tool_slow")
    elif fault == FAULT_CONTEXT_TRUNCATION:
        if genome.context_mode == "none":
            sym.append("lost_context")
        elif genome.context_mode == "truncated":
            sym.append("partial_context")
        else:
            sym.append("context_noise")
    elif fault == FAULT_PLAN_GAP:
        if "DIAGNOSE" not in e:
            sym.append("incomplete_plan")
        else:
            sym.append("plan_partial")
    else:
        sym.append("no_output")
    return sym


def diagnose_from_symptoms(symptoms: List[str], confidence_base: float = 0.55) -> Tuple[str, float]:
    """Observable diagnosis. Ambiguous symptoms → UNKNOWN or low confidence."""
    cats = []
    for s in symptoms:
        cats.extend(_SYMPTOM_MAP.get(s, (UNKNOWN,)))
    uniq = set(cats)
    if not uniq or uniq == {UNKNOWN}:
        return UNKNOWN, 0.2
    if len(uniq) > 2:
        return UNKNOWN, 0.3
    # pick most frequent, confidence reduced by ambiguity
    from collections import Counter

    c = Counter(cats).most_common(1)[0][0]
    ambig = 1.0 - (1.0 / len(uniq))
    conf = max(0.2, confidence_base - 0.25 * ambig)
    return c, conf


class ControlledEnv:
    """Deterministic mock evaluation of (genome, task) with injected faults."""

    def __init__(self, tasks: List[TaskInstance], seed: int = 0):
        self.tasks = tasks
        self.seed = seed

    def evaluate(self, genome: WorkflowGenome, task: TaskInstance) -> EvalResult:
        genome.validate()
        e = genome.enabled_kinds()
        sym = observable_symptoms(task.fault_type, genome)
        # reward: structural fit to the fault + slight preference for richer structure
        fit = 0.0
        if task.fault_type == FAULT_MISSING_VERIFY:
            fit = 1.0 if "VERIFY" in e else 0.0
        elif task.fault_type == FAULT_WRONG_RECOVERY:
            fit = 1.0 if "REPAIR" in e and genome.max_repairs >= 2 else (0.4 if "REPAIR" in e else 0.0)
        elif task.fault_type == FAULT_TOOL_ROUTING:
            fit = 1.0 if genome.route_policy == "verify_first" else 0.0
        elif task.fault_type == FAULT_CONTEXT_TRUNCATION:
            fit = 1.0 if genome.context_mode == "full" else (0.3 if genome.context_mode == "truncated" else 0.0)
        elif task.fault_type == FAULT_PLAN_GAP:
            fit = 1.0 if "DIAGNOSE" in e else 0.0
        # cost penalty so "add everything" is not free
        complexity = sum(1 for n in genome.nodes if n.enabled) * 0.02
        reward = max(0.0, fit - complexity * (1.0 + task.difficulty * 0.3))
        success = reward > 0.55
        return EvalResult(
            task_id=task.task_id,
            genome_id=genome.hash(),
            success=success,
            reward=reward,
            symptoms=sym,
            trace_id=f"{task.task_id}:{genome.hash()}",
            fault_type=task.fault_type,
        )

    def observe_failure(self, res: EvalResult, genome: WorkflowGenome) -> FailureEvidence:
        """Build policy-visible evidence. NO fault_type leakage."""
        cat, conf = diagnose_from_symptoms(res.symptoms)
        return evidence_from_trace(
            task_id=res.task_id,
            genome_id=res.genome_id,
            symptoms=res.symptoms,
            trace_ids=[res.trace_id],
            diagnosed_category=cat,
            confidence=conf,
        )


def make_task_suite(n_per_fault: int = 8, seed: int = 0) -> List[TaskInstance]:
    """Frozen task generation rule (deterministic given seed)."""
    import random

    rng = random.Random(seed)
    tasks: List[TaskInstance] = []
    for fault in FAULT_TYPES:
        for i in range(n_per_fault):
            tid = f"{fault[:6].lower()}-{seed}-{i:02d}"
            tasks.append(
                TaskInstance(
                    task_id=tid,
                    fault_type=fault,
                    difficulty=rng.choice([0.3, 0.5, 0.7, 0.9]),
                    family=fault,
                )
            )
    return tasks


def split_tasks(tasks: List[TaskInstance], seed: int = 7):
    """Train / dev / heldout split by instance id — no near-duplicates across."""
    import random

    rng = random.Random(seed)
    idx = list(range(len(tasks)))
    rng.shuffle(idx)
    n = len(tasks)
    a = int(0.6 * n)
    b = int(0.8 * n)
    train = [tasks[i] for i in idx[:a]]
    dev = [tasks[i] for i in idx[a:b]]
    test = [tasks[i] for i in idx[b:]]
    return train, dev, test
