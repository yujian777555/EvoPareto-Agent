"""Offline evaluator for FCEOL controlled experiments (Stage 2.0)."""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.research.fceol.controlled_faults import (
    ControlledEnv,
    EvalResult,
    TaskInstance,
    make_task_suite,
    split_tasks,
)
from src.research.fceol.failure_evidence import FailureEvidence
from src.research.fceol.intervention_credit import InterventionRecord
from src.research.fceol.mutation_operators import MUTATION_OPERATORS, apply_operator
from src.research.fceol.operator_policy import (
    FailureConditionedHeuristic,
    FailureConditionedPolicy,
    GlobalAOS,
    OracleUpperBound,
    OperatorPolicy,
    RandomMutation,
    ShuffledFailurePolicy,
)
from src.research.fceol.workflow_genome import WorkflowGenome, base_genome


@dataclass
class RunStats:
    policy: str
    n_steps: int = 0
    n_success: int = 0
    n_improved: int = 0
    n_negative: int = 0
    n_invalid: int = 0
    sum_delta: float = 0.0
    operator_counts: Dict[str, int] = field(default_factory=dict)
    final_rewards: List[float] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "policy": self.policy,
            "n_steps": self.n_steps,
            "success_rate": self.n_success / self.n_steps if self.n_steps else 0.0,
            "improved_rate": self.n_improved / self.n_steps if self.n_steps else 0.0,
            "negative_rate": self.n_negative / self.n_steps if self.n_steps else 0.0,
            "invalid_rate": self.n_invalid / self.n_steps if self.n_steps else 0.0,
            "mean_delta": self.sum_delta / self.n_steps if self.n_steps else 0.0,
            "mean_final_reward": (sum(self.final_rewards) / len(self.final_rewards)) if self.final_rewards else 0.0,
            "operator_counts": dict(self.operator_counts),
        }


def run_policy_on_tasks(
    policy: OperatorPolicy,
    tasks: Sequence[TaskInstance],
    *,
    seed: int = 0,
    steps_per_task: int = 3,
    operators: Sequence[str] = MUTATION_OPERATORS,
    use_oracle_context: bool = False,
) -> RunStats:
    rng = random.Random(seed)
    env = ControlledEnv(list(tasks), seed=seed)
    stats = RunStats(policy=policy.name)
    g = base_genome()
    # baseline parent reward on first task of each family for pairing
    for task in tasks:
        parent_res = env.evaluate(g, task)
        stats.final_rewards.append(parent_res.reward)
        for step in range(steps_per_task):
            ev = env.observe_failure(parent_res, g)
            if use_oracle_context and isinstance(policy, OracleUpperBound):
                ev._oracle_op = {
                    "FAULT_MISSING_VERIFY": "M1_INSERT_VERIFICATION",
                    "FAULT_WRONG_RECOVERY": "M2_ADD_FAILURE_RECOVERY",
                    "FAULT_TOOL_ROUTING": "M3_CHANGE_TOOL_ROUTING",
                    "FAULT_CONTEXT_TRUNCATION": "M4_MODIFY_CONTEXT_FLOW",
                    "FAULT_PLAN_GAP": "M2_ADD_FAILURE_RECOVERY",
                }.get(parent_res.fault_type, "M1_INSERT_VERIFICATION")
            op = policy.select(ev, operators, rng)
            stats.operator_counts[op] = stats.operator_counts.get(op, 0) + 1
            child = apply_operator(op, g)
            if child is None:
                stats.n_invalid += 1
                stats.n_steps += 1
                continue
            child_res = env.evaluate(child, task)
            delta = child_res.reward - parent_res.reward
            stats.n_steps += 1
            stats.sum_delta += delta
            if child_res.success:
                stats.n_success += 1
            if delta > 1e-6:
                stats.n_improved += 1
            elif delta < -1e-6:
                stats.n_negative += 1
            policy.update(
                InterventionRecord(
                    failure_context=ev.context_key(),
                    operator=op,
                    parent_reward=parent_res.reward,
                    child_reward=child_res.reward,
                    task_id=task.task_id,
                )
            )
            if child_res.reward >= parent_res.reward:
                g = child  # accept non-worsening
                parent_res = child_res
            stats.final_rewards[-1] = parent_res.reward
    return stats


def heldout_transfer(policy: OperatorPolicy, tasks: Sequence[TaskInstance], seed: int = 1) -> RunStats:
    """Evaluate learned policy on unseen tasks without further updates? 
    We allow updates on heldout to measure online adaptation, but report separately.
    """
    return run_policy_on_tasks(policy, tasks, seed=seed, steps_per_task=2)


def run_full_experiment(seed: int = 42) -> Dict[str, Any]:
    """Frozen experiment: train on 60%, report held-out 20%."""
    tasks = make_task_suite(n_per_fault=8, seed=11)
    train, dev, test = split_tasks(tasks, seed=7)

    policies = {
        "random": lambda: RandomMutation(),
        "global_aos": lambda: GlobalAOS(),
        "fixed_map": lambda: FailureConditionedHeuristic(),
        "fceol": lambda: FailureConditionedPolicy(),
        "shuffled": lambda: ShuffledFailurePolicy(),
        "oracle": lambda: OracleUpperBound(),
    }

    train_stats = {}
    heldout_stats = {}
    for name, ctor in policies.items():
        pol = ctor()
        tr = run_policy_on_tasks(pol, train, seed=seed, steps_per_task=3,
                                 use_oracle_context=(name == "oracle"))
        train_stats[name] = tr.as_dict()
        ho = run_policy_on_tasks(pol, test, seed=seed + 1, steps_per_task=2,
                                 use_oracle_context=(name == "oracle"))
        heldout_stats[name] = ho.as_dict()

    return {
        "train": train_stats,
        "heldout": heldout_stats,
        "n_train": len(train),
        "n_dev": len(dev),
        "n_test": len(test),
        "operators": list(MUTATION_OPERATORS),
    }
