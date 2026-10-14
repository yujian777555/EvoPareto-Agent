"""Mutation experience model (Phase 2).

Learns mutation effectiveness from EvolutionArchive records.
Optimizer memory only — not agent/task memory.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from src.evolution.archive import EvolutionRecord


@dataclass
class MutationStats:
    count: int = 0
    success: int = 0
    improvement_sum: float = 0.0  # sum of hypervolume_delta on successes
    delta_norm_sum: float = 0.0  # sum of L1 positive objective gains

    @property
    def success_rate(self) -> float:
        return (self.success / self.count) if self.count else 0.0

    @property
    def average_improvement(self) -> float:
        return (self.improvement_sum / self.count) if self.count else 0.0

    @property
    def average_gain(self) -> float:
        return (self.delta_norm_sum / self.count) if self.count else 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "count": self.count,
            "success": self.success,
            "success_rate": self.success_rate,
            "average_improvement": self.average_improvement,
            "average_gain": self.average_gain,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, float]) -> "MutationStats":
        st = cls()
        st.count = int(data.get("count", 0))
        st.success = int(data.get("success", 0))
        st.improvement_sum = float(data.get("average_improvement", 0.0)) * st.count
        st.delta_norm_sum = float(data.get("average_gain", 0.0)) * st.count
        return st


class MutationExperience:
    """Accumulates per-mutation-type effectiveness statistics."""

    def __init__(
        self,
        *,
        prior_weight: float = 1.0,
        prior_success_rate: float = 0.35,
    ) -> None:
        self.stats: Dict[str, MutationStats] = {}
        self.prior_weight = float(prior_weight)
        self.prior_success_rate = float(prior_success_rate)

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #
    def update(self, record: EvolutionRecord) -> None:
        st = self.stats.setdefault(record.mutation_type, MutationStats())
        st.count += 1
        if record.success:
            st.success += 1
        # Improvement uses HV delta (clipped at 0 for averaging) plus L1 gain.
        hv_gain = max(0.0, record.hypervolume_delta)
        st.improvement_sum += hv_gain
        # Positive part of objective deltas as a local gain signal.
        gain = sum(max(0.0, d) for d in record.objective_delta)
        st.delta_norm_sum += gain

    def update_many(self, records: Iterable[EvolutionRecord]) -> None:
        for r in records:
            self.update(r)

    def update_from_archive(self, archive) -> None:
        self.update_many(archive.records)

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get_stats(self, mutation_type: str) -> MutationStats:
        return self.stats.get(mutation_type, MutationStats())

    def get_score(self, mutation_type: str) -> float:
        """Smoothed score used by the adaptive controller.

        score = (successes + prior) / (count + prior_weight)
                * (1 + average_improvement)
        """
        st = self.get_stats(mutation_type)
        smoothed = (st.success + self.prior_weight * self.prior_success_rate) / (
            st.count + self.prior_weight
        )
        return smoothed * (1.0 + max(0.0, st.average_improvement))

    def scores(self, mutation_types: Optional[Sequence[str]] = None) -> Dict[str, float]:
        types = list(mutation_types) if mutation_types is not None else sorted(self.stats)
        return {t: self.get_score(t) for t in types}

    def summary(self) -> Dict[str, Dict[str, float]]:
        return {t: st.to_dict() for t, st in sorted(self.stats.items())}

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, object]:
        return {
            "prior_weight": self.prior_weight,
            "prior_success_rate": self.prior_success_rate,
            "stats": {t: st.to_dict() for t, st in self.stats.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "MutationExperience":
        exp = cls(
            prior_weight=float(data.get("prior_weight", 1.0)),
            prior_success_rate=float(data.get("prior_success_rate", 0.35)),
        )
        for t, st in dict(data.get("stats", {})).items():
            exp.stats[t] = MutationStats.from_dict(st)  # type: ignore[arg-type]
        return exp

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "MutationExperience":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
