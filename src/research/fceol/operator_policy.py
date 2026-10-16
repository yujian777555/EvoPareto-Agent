"""Operator selection policies (Stage 2.0).

Baselines and FCEOL. Policy input = FailureEvidence.context_key() only —
never injected fault type or ground-truth best operator.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence

from src.research.fceol.failure_evidence import FailureEvidence
from src.research.fceol.intervention_credit import InterventionCredit, InterventionRecord
from src.research.fceol.mutation_operators import MUTATION_OPERATORS


class OperatorPolicy:
    name = "base"

    def select(self, evidence: FailureEvidence, operators: Sequence[str], rng: random.Random) -> str:
        raise NotImplementedError

    def update(self, rec: InterventionRecord) -> None:
        pass


class RandomMutation(OperatorPolicy):
    name = "random"

    def select(self, evidence, operators, rng):
        return rng.choice(list(operators))


class GlobalAOS(OperatorPolicy):
    """UCB1 over operators, ignoring failure context."""

    name = "global_aos"

    def __init__(self, c: float = 1.4):
        self.c = c
        self.credit = InterventionCredit()
        self.counts: Dict[str, int] = {}
        self.t = 0

    def select(self, evidence, operators, rng):
        ops = list(operators)
        self.t += 1
        for op in ops:
            if self.counts.get(op, 0) == 0:
                self.counts[op] = self.counts.get(op, 0) + 0  # touch
                self._n = getattr(self, "_n", {})
                return op
        best, best_v = ops[0], -1e9
        for op in ops:
            n = self.counts.get(op, 1)
            mean = self.credit.mean_credit("global", op)
            v = mean + self.c * math.sqrt(math.log(self.t) / n)
            if v > best_v:
                best, best_v = op, v
        return best

    def update(self, rec: InterventionRecord) -> None:
        g = InterventionRecord("global", rec.operator, rec.parent_reward, rec.child_reward, rec.task_id)
        self.credit.update(g)
        self.counts[rec.operator] = self.counts.get(rec.operator, 0) + 1


class FailureConditionedHeuristic(OperatorPolicy):
    """Fixed failure→operator map (no learning)."""

    name = "fixed_map"
    MAP = {
        "ctx:VERIFICATION_FAILURE:hi": "M1_INSERT_VERIFICATION",
        "ctx:VERIFICATION_FAILURE:md": "M1_INSERT_VERIFICATION",
        "ctx:RECOVERY_FAILURE:hi": "M2_ADD_FAILURE_RECOVERY",
        "ctx:RECOVERY_FAILURE:md": "M2_ADD_FAILURE_RECOVERY",
        "ctx:TOOL_SELECTION_FAILURE:hi": "M3_CHANGE_TOOL_ROUTING",
        "ctx:TOOL_SELECTION_FAILURE:md": "M3_CHANGE_TOOL_ROUTING",
        "ctx:CONTEXT_FAILURE:hi": "M4_MODIFY_CONTEXT_FLOW",
        "ctx:CONTEXT_FAILURE:md": "M4_MODIFY_CONTEXT_FLOW",
        "ctx:PLANNING_FAILURE:hi": "M2_ADD_FAILURE_RECOVERY",
        "ctx:PLANNING_FAILURE:md": "M1_INSERT_VERIFICATION",
    }

    def select(self, evidence, operators, rng):
        op = self.MAP.get(evidence.context_key())
        if op and op in operators:
            return op
        return rng.choice(list(operators))


class FailureConditionedPolicy(OperatorPolicy):
    """FCEOL: UCB conditioned on failure-context key + intervention credit.

    Honest framing: this is a contextual bandit-style operator policy over
    failure contexts. Novelty is in the failure-evidence representation and
    paired intervention credit — not in inventing bandits.
    """

    name = "fceol"
    EXPLORATION_UNKNOWN = 1.8  # higher exploration for UNKNOWN contexts

    def __init__(self, c: float = 1.4):
        self.c = c
        self.credit = InterventionCredit()
        self.counts: Dict[str, Dict[str, int]] = {}
        self.t: Dict[str, int] = {}

    def select(self, evidence, operators, rng):
        ctx = evidence.context_key()
        ops = list(operators)
        self.t[ctx] = self.t.get(ctx, 0) + 1
        counts = self.counts.setdefault(ctx, {})
        for op in ops:
            if counts.get(op, 0) == 0:
                counts[op] = 1
                self.counts[ctx] = counts
                return op
        c = self.EXPLORATION_UNKNOWN if ctx == "ctx:UNKNOWN" else self.c
        best, best_v = ops[0], -1e9
        t = self.t[ctx]
        for op in ops:
            n = counts.get(op, 1)
            mean = self.credit.mean_credit(ctx, op)
            v = mean + c * math.sqrt(math.log(max(2, t)) / n)
            if v > best_v:
                best, best_v = op, v
        return best

    def update(self, rec: InterventionRecord) -> None:
        self.credit.update(rec)
        counts = self.counts.setdefault(rec.failure_context, {})
        counts[rec.operator] = counts.get(rec.operator, 0) + 1


class ShuffledFailurePolicy(FailureConditionedPolicy):
    """Same as FCEOL but context keys are independently shuffled (control)."""

    name = "shuffled"
    _SHUFFLE_SALT = 97

    def select(self, evidence, operators, rng):
        fake = FailureEvidence(
            task_id=evidence.task_id,
            genome_id=evidence.genome_id,
            failure_category=evidence.failure_category,
            observed_symptoms=evidence.observed_symptoms,
            diagnostic_confidence=evidence.diagnostic_confidence,
            unknown_flag=evidence.unknown_flag,
        )
        # deterministic wrong context derived from task_id hash — not truth
        keys = list(self.credit.snapshot().keys()) or ["ctx:UNKNOWN"]
        idx = (hash(fake.task_id) + self._SHUFFLE_SALT) % max(1, len(keys))
        ctx = keys[idx]
        ops = list(operators)
        counts = self.counts.setdefault(ctx, {})
        self.t[ctx] = self.t.get(ctx, 0) + 1
        for op in ops:
            if counts.get(op, 0) == 0:
                counts[op] = 1
                return op
        best, best_v = ops[0], -1e9
        for op in ops:
            n = counts.get(op, 1)
            mean = self.credit.mean_credit(ctx, op)
            v = mean + self.c * math.sqrt(math.log(max(2, self.t[ctx])) / n)
            if v > best_v:
                best, best_v = op, v
        return best


class OracleUpperBound(OperatorPolicy):
    """ISOLATED offline upper bound: reads ground truth. NEVER a deployable policy."""

    name = "oracle"

    def select(self, evidence, operators, rng):
        # mapping used only for ceiling estimation
        best = {
            "FAULT_MISSING_VERIFY": "M1_INSERT_VERIFICATION",
            "FAULT_WRONG_RECOVERY": "M2_ADD_FAILURE_RECOVERY",
            "FAULT_TOOL_ROUTING": "M3_CHANGE_TOOL_ROUTING",
            "FAULT_CONTEXT_TRUNCATION": "M4_MODIFY_CONTEXT_FLOW",
            "FAULT_PLAN_GAP": "M2_ADD_FAILURE_RECOVERY",
        }
        # evidence carries no fault; caller passes via side channel in evaluator
        op = getattr(evidence, "_oracle_op", None)
        return op if op in operators else rng.choice(list(operators))
