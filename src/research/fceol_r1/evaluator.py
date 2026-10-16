"""Strict evaluation protocols (P0-4, P0-6)."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.research.fceol.mutation_operators import MUTATION_OPERATORS, apply_operator
from src.research.fceol.workflow_genome import WorkflowGenome, base_genome
from src.research.fceol_r1.evidence import Evidence, build_evidence
from src.research.fceol_r1.faults import fault_channels
from src.research.fceol_r1.policies import FCEOL, FixedMap, GlobalAOS, OracleBest, Policy, RandomPolicy
from src.research.fceol_r1.task_suite import TaskInstance
from src.research.fceol_r1.workflow_interpreter import WorkflowInterpreter


@dataclass
class StepRecord:
    task_id: str
    context_key: str
    operator: str
    parent_reward: float
    child_reward: float
    delta: float
    genome_before: str
    genome_after: str
    symptoms: List[str]


@dataclass
class TaskResult:
    task_id: str
    final_reward: float
    success: bool
    steps: int
    deltas: List[float] = field(default_factory=list)
    ops: List[str] = field(default_factory=list)


def eval_genome(genome: WorkflowGenome, task: TaskInstance):
    """Run interpreter; returns (state, reward)."""
    interp = WorkflowInterpreter(genome)
    channels = fault_channels(task)
    return interp.run(task, channels)


def operator_learning_protocol(
    policy: Policy,
    tasks: Sequence[TaskInstance],
    *,
    seed: int = 0,
    steps_per_task: int = 2,
    evidence_mode: str = "TRUE_EVIDENCE",
    freeze_policy: bool = True,
    operators: Sequence[str] = MUTATION_OPERATORS,
) -> Dict[str, Any]:
    """Experiment 1: paired parent/child under same initial genome per task.

    freeze_policy=True → Protocol A (Frozen Transfer): no updates on these tasks.
    freeze_policy=False → Protocol B (Online Adaptation): updates allowed.
    """
    rng = random.Random(seed)
    if freeze_policy and hasattr(policy, "freeze"):
        policy.freeze()
    steps: List[StepRecord] = []
    task_results: List[TaskResult] = []
    for task in tasks:
        parent = base_genome()
        _, pr = eval_genome(parent, task)
        tr = TaskResult(task.task_id, pr, pr > 0.55, 0)
        for s in range(steps_per_task):
            st, _ = eval_genome(parent, task)
            ev = build_evidence(task_id=task.policy_task_id(), symptoms=st.symptoms,
                                mode=evidence_mode, seed=seed)
            op = policy.select(ev, operators, rng)
            child = apply_operator(op, parent)
            if child is None:
                tr.deltas.append(0.0)
                continue
            _, cr = eval_genome(child, task)
            delta = cr - pr
            steps.append(StepRecord(task.task_id, ev.context_key, op, pr, cr, delta,
                                    parent.hash(), child.hash(), st.symptoms))
            policy.update(ev.context_key, op, delta)
            tr.deltas.append(delta)
            tr.ops.append(op)
            tr.steps += 1
            if cr >= pr:
                parent, pr = child, cr
        tr.final_reward = pr
        tr.success = pr > 0.55
        task_results.append(tr)

    finals = [t.final_reward for t in task_results]
    succ = [1.0 if t.success else 0.0 for t in task_results]
    deltas = [s.delta for s in steps]
    n = max(1, len(finals))
    return {
        "protocol": "frozen_transfer" if freeze_policy else "online_adaptation",
        "evidence_mode": evidence_mode,
        "policy": policy.name,
        "n_tasks": len(task_results),
        "n_steps": len(steps),
        "mean_final_reward": sum(finals) / n,
        "task_success_rate": sum(succ) / n,
        "mean_paired_delta": (sum(deltas) / len(deltas)) if deltas else 0.0,
        "improvement_prob": (sum(1 for d in deltas if d > 1e-6) / len(deltas)) if deltas else 0.0,
        "negative_rate": (sum(1 for d in deltas if d < -1e-6) / len(deltas)) if deltas else 0.0,
        "task_results": [
            {"task_id": t.task_id, "final_reward": t.final_reward,
             "success": t.success, "steps": t.steps, "ops": t.ops}
            for t in task_results
        ],
        "steps": [
            {"task_id": s.task_id, "ctx": s.context_key, "op": s.operator,
             "delta": s.delta, "parent": s.parent_reward, "child": s.child_reward}
            for s in steps
        ],
    }


def oracle_upper_bound(tasks: Sequence[TaskInstance], budget: int = 2) -> Dict[str, Any]:
    """Exact enumeration per task from same initial genome."""
    finals = []
    for task in tasks:
        oracle = OracleBest(eval_genome, budget=budget)
        seq, r, _ = oracle.plan(task, base_genome(), fault_channels(task), MUTATION_OPERATORS)
        finals.append({"task_id": task.task_id, "best_reward": r, "best_seq": seq})
    vals = [f["best_reward"] for f in finals]
    return {
        "n_tasks": len(tasks),
        "mean_best_reward": sum(vals) / max(1, len(vals)),
        "per_task": finals,
        "note": "exact enumeration upper bound on final reward with same budget",
    }
