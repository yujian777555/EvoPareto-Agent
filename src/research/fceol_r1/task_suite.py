"""Task suite with globally unique IDs and template-grouped splits (P0-1).

task_id = f"{fault_type}~{seed}~{instance_index:04d}"  — full fault name
included so IDs are unique across fault types. Splits are grouped by
template_id so near-duplicate templates never cross splits.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence, Tuple

FAULT_VERIFICATION_OMISSION = "VERIFICATION_OMISSION"
FAULT_RECOVERY_BRANCH_ERROR = "RECOVERY_BRANCH_ERROR"
FAULT_TOOL_ROUTING_ERROR = "TOOL_ROUTING_ERROR"
FAULT_CONTEXT_PROPAGATION_ERROR = "CONTEXT_PROPAGATION_ERROR"
FAULT_COMPOUND = "COMPOUND_RECOVERY_ROUTING"  # two faults at once

FAULT_TYPES = (
    FAULT_VERIFICATION_OMISSION,
    FAULT_RECOVERY_BRANCH_ERROR,
    FAULT_TOOL_ROUTING_ERROR,
    FAULT_CONTEXT_PROPAGATION_ERROR,
    FAULT_COMPOUND,
)


@dataclass
class TaskInstance:
    task_id: str
    template_id: str
    fault_type: str          # ground truth — NOT given to policy
    seed: int
    instance_index: int
    difficulty: float
    # executable problem definition (visible to interpreter, not fault label)
    goal_spec: str = "produce a solution passing independent checks"
    required_checks: Tuple[str, ...] = ("consistency", "completeness")
    tool_catalog: Tuple[str, ...] = ("tool_a", "tool_b")
    correct_tool: str = "tool_a"
    constraint_key: str = "C1"
    base_output_quality: float = 0.25  # quality of naive GENERATE

    def unique_key(self) -> str:
        return f"{self.fault_type}|{self.seed}|{self.instance_index:04d}"

    def policy_task_id(self) -> str:
        """Opaque id for policy-visible evidence (no fault string)."""
        h = hashlib.sha256(self.unique_key().encode()).hexdigest()[:12]
        return f"task-{h}"

    def public_dict(self) -> Dict[str, Any]:
        """Policy-visible subset — no fault_type."""
        return {
            "task_id": self.task_id,
            "goal_spec": self.goal_spec,
            "required_checks": list(self.required_checks),
            "tool_catalog": list(self.tool_catalog),
            "constraint_key": self.constraint_key,
        }


def make_task_suite(
    *, n_per_fault: int = 6, seed: int = 11, difficulty_levels: Sequence[float] = (0.3, 0.5, 0.7)
) -> List[TaskInstance]:
    """Deterministic generation. Each (fault, seed, i) is one instance.

    Template id groups share the same fault *family* and difficulty so we
    can do template-grouped splits (no near-duplicate leakage).
    """
    tasks: List[TaskInstance] = []
    for fault in FAULT_TYPES:
        for i in range(n_per_fault):
            diff = difficulty_levels[i % len(difficulty_levels)]
            # template groups 2 consecutive instances of same fault+difficulty
            tmpl = f"T-{fault[:12]}-D{int(diff * 10):02d}-{(i // 2):02d}"
            correct_tool = "tool_a" if (i + seed) % 2 == 0 else "tool_b"
            tasks.append(
                TaskInstance(
                    task_id=f"{fault}~{seed}~{i:04d}",
                    template_id=tmpl,
                    fault_type=fault,
                    seed=seed,
                    instance_index=i,
                    difficulty=diff,
                    correct_tool=correct_tool,
                    constraint_key=f"C{(i % 3) + 1}",
                    base_output_quality=round(0.15 + 0.1 * diff, 3),
                )
            )
    return tasks


def split_by_template(
    tasks: Sequence[TaskInstance], *, seed: int = 7
) -> Tuple[List[TaskInstance], List[TaskInstance], List[TaskInstance]]:
    """Group by template_id, then split groups 60/20/20. No cross-split templates."""
    by_t: Dict[str, List[TaskInstance]] = {}
    for t in tasks:
        by_t.setdefault(t.template_id, []).append(t)
    templates = sorted(by_t.keys())
    rng = random.Random(seed)
    rng.shuffle(templates)
    n = len(templates)
    a = max(1, int(0.6 * n))
    b = max(a + 1, int(0.8 * n))
    train_t, dev_t, test_t = set(templates[:a]), set(templates[a:b]), set(templates[b:])
    train = [t for t in tasks if t.template_id in train_t]
    dev = [t for t in tasks if t.template_id in dev_t]
    test = [t for t in tasks if t.template_id in test_t]
    return train, dev, test


def audit_splits(
    tasks: Sequence[TaskInstance],
    train: Sequence[TaskInstance],
    dev: Sequence[TaskInstance],
    test: Sequence[TaskInstance],
) -> Dict[str, Any]:
    ids = [t.task_id for t in tasks]
    uniq = set(ids)
    tr, dv, te = {t.task_id for t in train}, {t.task_id for t in dev}, {t.task_id for t in test}
    ttr = {t.template_id for t in train}
    tdv = {t.template_id for t in dev}
    tte = {t.template_id for t in test}
    return {
        "total_tasks": len(tasks),
        "unique_id_count": len(uniq),
        "unique_id_pass": len(uniq) == len(tasks),
        "train_dev_disjoint": tr.isdisjoint(dv),
        "train_test_disjoint": tr.isdisjoint(te),
        "dev_test_disjoint": dv.isdisjoint(te),
        "template_train_test_disjoint": ttr.isdisjoint(tte),
        "template_train_dev_disjoint": ttr.isdisjoint(tdv),
        "template_dev_test_disjoint": tdv.isdisjoint(tte),
        "n_train": len(train),
        "n_dev": len(dev),
        "n_test": len(test),
    }
