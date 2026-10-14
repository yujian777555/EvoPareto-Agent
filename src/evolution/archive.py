"""EvolutionArchive: store evolutionary transitions (Phase 2).

This is **optimizer memory**, not agent/task memory. No RAG, no vector DB.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from src.evaluation.metrics import hypervolume


@dataclass
class EvolutionRecord:
    """One parent -> child mutation transition.

    Phase 2 fields retained for compatibility. Phase 2.5 adds Pareto-aware
    credit fields (optional; default 0 / False).
    """

    generation: int
    parent_genome_id: str
    child_genome_id: str
    mutation_type: str
    parent_objectives: List[float]
    child_objectives: List[float]
    objective_delta: List[float]
    hypervolume_delta: float
    success: bool
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Phase 2.5 Pareto-aware credits
    pareto_rank_change: int = 0
    hypervolume_contribution: float = 0.0
    diversity_contribution: float = 0.0
    survived_next_generation: bool = False
    mutation_value: float = 0.0

    def __post_init__(self) -> None:
        self.parent_objectives = [float(x) for x in self.parent_objectives]
        self.child_objectives = [float(x) for x in self.child_objectives]
        self.objective_delta = [float(x) for x in self.objective_delta]
        self.hypervolume_delta = float(self.hypervolume_delta)
        self.hypervolume_contribution = float(self.hypervolume_contribution)
        self.diversity_contribution = float(self.diversity_contribution)
        self.mutation_value = float(self.mutation_value)
        self.pareto_rank_change = int(self.pareto_rank_change)
        if len(self.parent_objectives) != len(self.child_objectives):
            raise ValueError("parent/child objective dimension mismatch")
        if len(self.objective_delta) != len(self.parent_objectives):
            raise ValueError("objective_delta dimension mismatch")

    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvolutionRecord":
        return cls(
            generation=int(data["generation"]),
            parent_genome_id=str(data["parent_genome_id"]),
            child_genome_id=str(data["child_genome_id"]),
            mutation_type=str(data["mutation_type"]),
            parent_objectives=[float(x) for x in data["parent_objectives"]],
            child_objectives=[float(x) for x in data["child_objectives"]],
            objective_delta=[float(x) for x in data["objective_delta"]],
            hypervolume_delta=float(data["hypervolume_delta"]),
            success=bool(data["success"]),
            metadata=dict(data.get("metadata", {})),
            pareto_rank_change=int(data.get("pareto_rank_change", 0)),
            hypervolume_contribution=float(data.get("hypervolume_contribution", 0.0)),
            diversity_contribution=float(data.get("diversity_contribution", 0.0)),
            survived_next_generation=bool(data.get("survived_next_generation", False)),
            mutation_value=float(data.get("mutation_value", 0.0)),
        )


def objective_delta(
    parent: Sequence[float], child: Sequence[float]
) -> List[float]:
    """child - parent in raw paper-semantics objective space."""
    return [float(c) - float(p) for p, c in zip(parent, child)]


def is_successful_transition(
    parent: Sequence[float],
    child: Sequence[float],
    *,
    hv_delta: Optional[float] = None,
    hv_threshold: float = 0.0,
) -> bool:
    """Success = child mixed-dominates parent OR positive HV delta.

    Mixed dominance uses paper semantics (max except cost).
    """
    from src.utils.pareto import dominates_mixed

    if dominates_mixed(child, parent):
        return True
    if hv_delta is not None and hv_delta > hv_threshold:
        return True
    return False


class EvolutionArchive:
    """Persistent log of evolutionary transitions + running HV baseline."""

    def __init__(self, records: Optional[Iterable[EvolutionRecord]] = None) -> None:
        self.records: List[EvolutionRecord] = list(records or [])
        self._front: List[List[float]] = []

    # ------------------------------------------------------------------ #
    # Write
    # ------------------------------------------------------------------ #
    def add(self, record: EvolutionRecord) -> None:
        self.records.append(record)

    def extend(self, records: Iterable[EvolutionRecord]) -> None:
        self.records.extend(records)

    def record_transition(
        self,
        *,
        generation: int,
        parent_genome_id: str,
        child_genome_id: str,
        mutation_type: str,
        parent_objectives: Sequence[float],
        child_objectives: Sequence[float],
        hv_delta: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> EvolutionRecord:
        parent = [float(x) for x in parent_objectives]
        child = [float(x) for x in child_objectives]
        delta = objective_delta(parent, child)
        if hv_delta is None:
            # Cheap incremental HV delta: exact-ish but small MC budget.
            hv_before = hypervolume(self._front or [parent], n_samples=512, seed=generation)
            hv_after = hypervolume(
                self._front + [child] if self._front else [parent, child],
                n_samples=512,
                seed=generation,
            )
            hv_delta = hv_after - hv_before
        success = is_successful_transition(parent, child, hv_delta=hv_delta)
        rec = EvolutionRecord(
            generation=generation,
            parent_genome_id=str(parent_genome_id),
            child_genome_id=str(child_genome_id),
            mutation_type=mutation_type,
            parent_objectives=parent,
            child_objectives=child,
            objective_delta=delta,
            hypervolume_delta=float(hv_delta),
            success=success,
            metadata=dict(metadata or {}),
        )
        self.add(rec)
        # Maintain a non-dominated objective cache for HV deltas.
        self._refresh_front(child)
        return rec

    def _refresh_front(self, candidate: Sequence[float]) -> None:
        from src.utils.pareto import pareto_mask_mixed

        pool = self._front + [[float(x) for x in candidate]]
        mask = pareto_mask_mixed(pool)
        self._front = [pool[i] for i in range(len(pool)) if mask[i]]

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.records)

    def by_mutation(self, mutation_type: str) -> List[EvolutionRecord]:
        return [r for r in self.records if r.mutation_type == mutation_type]

    def mutation_types(self) -> List[str]:
        return sorted({r.mutation_type for r in self.records})

    def front(self) -> List[List[float]]:
        return [list(p) for p in self._front]

    def summary(self) -> Dict[str, Any]:
        n = len(self.records)
        n_ok = sum(1 for r in self.records if r.success)
        return {
            "n_records": n,
            "n_success": n_ok,
            "success_rate": (n_ok / n) if n else 0.0,
            "mutation_types": self.mutation_types(),
            "front_size": len(self._front),
        }

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "front": self._front,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvolutionArchive":
        arch = cls(EvolutionRecord.from_dict(r) for r in data.get("records", []))
        arch._front = [[float(x) for x in p] for p in data.get("front", [])]
        return arch

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "EvolutionArchive":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)
