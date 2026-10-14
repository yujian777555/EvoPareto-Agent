"""Delayed credit assignment (Phase 2.5-R1).

A mutation at generation t may only become valuable at t+k (e.g. enter the
Pareto front later). Records carry:

    mutation_id
    future_survival
    future_pareto_gain

and can be retroactively updated when descendants survive or join the front.
"""

from __future__ import annotations

import itertools
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.utils.pareto import dominates_mixed


_MUTATION_SEQ = itertools.count(1)


def new_mutation_id() -> str:
    return f"m{next(_MUTATION_SEQ):06d}-{uuid.uuid4().hex[:8]}"


@dataclass
class DelayedCreditBook:
    """Tracks open mutations and applies future survival / Pareto gains."""

    horizon: int = 3  # generations to keep watching
    records: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def register(
        self,
        mutation_id: str,
        *,
        generation: int,
        mutation_type: str,
        child_objectives: Sequence[float],
        immediate_mv: float = 0.0,
        genome_id: str = "",
    ) -> str:
        self.records[mutation_id] = {
            "mutation_id": mutation_id,
            "generation": generation,
            "mutation_type": mutation_type,
            "child_objectives": [float(x) for x in child_objectives],
            "genome_id": genome_id,
            "immediate_mv": float(immediate_mv),
            "future_survival": 0.0,
            "future_pareto_gain": 0.0,
            "age": 0,
            "closed": False,
        }
        return mutation_id

    def step(self, *, generation: int) -> None:
        """Advance the book one generation; expire old entries."""
        for rec in self.records.values():
            if rec["closed"]:
                continue
            rec["age"] = int(rec["generation"]) - int(generation)
            if generation - int(rec["generation"]) > self.horizon:
                rec["closed"] = True

    def observe_population(
        self,
        population: Sequence[Sequence[float]],
        *,
        generation: int,
    ) -> None:
        """Score open mutations against the current population.

        - future_survival += 1 if child still competitive
        - future_pareto_gain += 1 if child would be non-dominated vs pop
        """
        if not population:
            return
        pop = [list(map(float, p)) for p in population]
        n_pop = len(pop)
        for rec in self.records.values():
            if rec.get("closed"):
                continue
            child = rec["child_objectives"]
            dominators = 0
            nd = True
            for p in pop:
                if dominates_mixed(p, child):
                    dominators += 1
                    nd = False
            if dominators < max(1, n_pop // 3):
                rec["future_survival"] += 1.0
            if nd:
                rec["future_pareto_gain"] += 1.0
            if generation - int(rec["generation"]) > self.horizon:
                rec["closed"] = True
        # Keep the book small.
        if len(self.records) > 200:
            self.clear_closed()

    def get(self, mutation_id: str) -> Optional[Dict[str, Any]]:
        return self.records.get(mutation_id)

    def delayed_bonus(self, mutation_id: str, *, w_survival: float = 0.15, w_pareto: float = 0.25) -> float:
        rec = self.records.get(mutation_id)
        if not rec:
            return 0.0
        return w_survival * float(rec["future_survival"]) + w_pareto * float(rec["future_pareto_gain"])

    def total_value(self, mutation_id: str, *, w_survival: float = 0.15, w_pareto: float = 0.25) -> float:
        rec = self.records.get(mutation_id)
        if not rec:
            return 0.0
        return float(rec["immediate_mv"]) + self.delayed_bonus(
            mutation_id, w_survival=w_survival, w_pareto=w_pareto
        )

    def type_aggregates(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for rec in self.records.values():
            t = str(rec["mutation_type"])
            slot = out.setdefault(t, {"n": 0.0, "immediate": 0.0, "future_survival": 0.0, "future_pareto_gain": 0.0})
            slot["n"] += 1
            slot["immediate"] += float(rec["immediate_mv"])
            slot["future_survival"] += float(rec["future_survival"])
            slot["future_pareto_gain"] += float(rec["future_pareto_gain"])
        return out

    def clear_closed(self) -> int:
        dead = [k for k, v in self.records.items() if v.get("closed")]
        for k in dead:
            del self.records[k]
        return len(dead)

    def to_dict(self) -> Dict[str, Any]:
        return {"horizon": self.horizon, "records": dict(self.records)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DelayedCreditBook":
        book = cls(horizon=int(data.get("horizon", 3)))
        book.records = {k: dict(v) for k, v in dict(data.get("records", {})).items()}
        return book
