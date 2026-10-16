"""Operator selection policies (P0-3 fixed controls)."""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

from src.research.fceol.mutation_operators import MUTATION_OPERATORS
from src.research.fceol_r1.evidence import Evidence

# simple online mean credit, conditioned or not
class _CreditTable:
    def __init__(self, decay: float = 0.35, prior: float = 0.0):
        self.decay = decay
        self.prior = prior
        self._s: Dict[str, float] = {}
        self._w: Dict[str, float] = {}
        self._n: Dict[str, int] = {}

    def key(self, ctx: str, op: str) -> str:
        return f"{ctx}||{op}"

    def update(self, ctx: str, op: str, delta: float) -> None:
        k = self.key(ctx, op)
        w = self.decay + (1 - self.decay) * self._w.get(k, 1.0)
        s = self.decay * delta + (1 - self.decay) * self._s.get(k, self.prior)
        self._w[k] = w
        self._s[k] = s
        self._n[k] = self._n.get(k, 0) + 1

    def mean(self, ctx: str, op: str) -> float:
        k = self.key(ctx, op)
        if k not in self._s:
            return self.prior
        return self._s[k] / (self._w[k] or 1.0)

    def n(self, ctx: str, op: str) -> int:
        return self._n.get(self.key(ctx, op), 0)


class Policy:
    name = "base"

    def select(self, ev: Evidence, operators: Sequence[str], rng: random.Random) -> str:
        raise NotImplementedError

    def update(self, ctx: str, op: str, delta: float) -> None:
        pass

    def freeze(self) -> None:
        """Disable learning (Protocol A)."""
        self.frozen = True


class RandomPolicy(Policy):
    name = "random"

    def select(self, ev, operators, rng):
        return rng.choice(list(operators))


class GlobalAOS(Policy):
    name = "global_aos"

    def __init__(self, c: float = 1.25):
        self.c = c
        self.credit = _CreditTable()
        self.t = 0
        self.frozen = False

    def select(self, ev, operators, rng):
        ops = list(operators)
        self.t += 1
        for op in ops:
            if self.credit.n("global", op) == 0:
                return op
        best, bv = ops[0], -1e9
        for op in ops:
            v = self.credit.mean("global", op) + self.c * math.sqrt(math.log(self.t + 1) / self.credit.n("global", op))
            if v > bv:
                best, bv = op, v
        return best

    def update(self, ctx, op, delta):
        if self.frozen:
            return
        self.credit.update("global", op, delta)


class FixedMap(Policy):
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

    def select(self, ev, operators, rng):
        op = self.MAP.get(ev.context_key)
        return op if op in operators else rng.choice(list(operators))


class ContextualUCB(Policy):
    """Standard contextual bandit UCB — strong baseline (P0 comparison)."""

    name = "contextual_bandit"

    def __init__(self, c: float = 1.25):
        self.c = c
        self.credit = _CreditTable()
        self.t: Dict[str, int] = {}
        self.frozen = False

    def select(self, ev, operators, rng):
        ctx = ev.context_key
        ops = list(operators)
        self.t[ctx] = self.t.get(ctx, 0) + 1
        for op in ops:
            if self.credit.n(ctx, op) == 0:
                return op
        best, bv = ops[0], -1e9
        for op in ops:
            v = self.credit.mean(ctx, op) + self.c * math.sqrt(math.log(self.t[ctx] + 1) / self.credit.n(ctx, op))
            if v > bv:
                best, bv = op, v
        return best

    def update(self, ctx, op, delta):
        if self.frozen:
            return
        self.credit.update(ctx, op, delta)


class FCEOL(Policy):
    """Failure-conditioned UCB; UNKNOWN gets wider exploration."""

    name = "fceol"

    def __init__(self, c: float = 1.25, c_unknown: float = 1.8):
        self.c = c
        self.c_unknown = c_unknown
        self.credit = _CreditTable()
        self.t: Dict[str, int] = {}
        self.frozen = False

    def select(self, ev, operators, rng):
        ctx = ev.context_key
        ops = list(operators)
        self.t[ctx] = self.t.get(ctx, 0) + 1
        for op in ops:
            if self.credit.n(ctx, op) == 0:
                return op
        c = self.c_unknown if ctx == "ctx:UNKNOWN" else self.c
        best, bv = ops[0], -1e9
        for op in ops:
            v = self.credit.mean(ctx, op) + c * math.sqrt(math.log(self.t[ctx] + 1) / self.credit.n(ctx, op))
            if v > bv:
                best, bv = op, v
        return best

    def update(self, ctx, op, delta):
        if self.frozen:
            return
        self.credit.update(ctx, op, delta)


class ShuffledEvidencePolicy(ContextualUCB):
    """Same learner as contextual bandit but context comes from the
    SHUFFLED evidence object (permutation applied upstream)."""

    name = "shuffled"


class OracleBest:
    """Exact enumeration upper bound for remaining budget (P0-5).

    Enumerates operator sequences up to `budget` steps from the *same*
    initial genome, picks max final reward. Uses ground truth only here.
    """

    name = "oracle"

    def __init__(self, evaluator, budget: int = 2):
        self.eval = evaluator
        self.budget = budget

    def select(self, ev, operators, rng):
        # unused: oracle computes a plan once
        return rng.choice(list(operators))

    def plan(self, task, genome, channels, operators):
        from src.research.fceol.mutation_operators import apply_operator

        best_seq: List[str] = []
        best_reward = -1.0
        best_final = genome
        ev = self.eval  # signature: (genome, task) -> (state, reward)

        def rec(g, seq, depth):
            nonlocal best_seq, best_reward, best_final
            _, r = ev(g, task)
            if r > best_reward:
                best_reward, best_seq, best_final = r, list(seq), g
            if depth >= self.budget:
                return
            for op in operators:
                ng = apply_operator(op, g)
                if ng is None:
                    continue
                seq.append(op)
                rec(ng, seq, depth + 1)
                seq.pop()

        rec(genome, [], 0)
        return best_seq, best_reward, best_final
