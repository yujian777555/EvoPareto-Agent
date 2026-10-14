"""Pareto-aware Evolution Experience Memory (PEEM) — Phase 2.5.

Learns mutation utility from:
  - Pareto improvement (objective / rank)
  - Hypervolume contribution
  - Diversity contribution
  - Survival feedback (retained by NSGA-III)

Scores use **exponential decay** so early mistakes do not dominate forever:

    score_t = λ * current_batch + (1 - λ) * score_{t-1}

Optimizer memory only — not agent memory / RAG / vector DB.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.evolution.credit_assignment import (
    CreditWeights,
    compute_credit,
)
from src.evolution.experience import MutationExperience, MutationStats


@dataclass
class PEEMConfig:
    """Decay and scoring configuration."""

    decay: float = 0.35  # λ: weight of the newest batch
    prior_weight: float = 1.5
    prior_value: float = 0.3
    min_score: float = 1e-3
    weights: CreditWeights = field(default_factory=CreditWeights)


@dataclass
class MutationUtility:
    """Decayed composite utility estimate for one mutation type."""

    value: float
    n_updates: int = 0
    last_mv: float = 0.0
    components: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "n_updates": self.n_updates,
            "last_mv": self.last_mv,
            "components": dict(self.components),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MutationUtility":
        return cls(
            value=float(data.get("value", 0.0)),
            n_updates=int(data.get("n_updates", 0)),
            last_mv=float(data.get("last_mv", 0.0)),
            components=dict(data.get("components", {})),
        )


class ParetoExperience:
    """PEEM: Pareto-aware Evolution Experience Memory.

    Compatible with Phase 2 `MutationExperience` (also accepts raw
    EvolutionRecord via `update_record`).
    """

    def __init__(self, config: Optional[PEEMConfig] = None) -> None:
        self.config = config or PEEMConfig()
        self.utility: Dict[str, MutationUtility] = {}
        self.history_mv: Dict[str, List[float]] = {}
        # Back-compat: keep Phase 2 success-rate stats view.
        self._legacy = MutationExperience(
            prior_weight=self.config.prior_weight,
            prior_success_rate=self.config.prior_value,
        )

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #
    def update(
        self,
        mutation_type: str,
        *,
        parent_objectives: Sequence[float],
        child_objectives: Sequence[float],
        population_front: Optional[Sequence[Sequence[float]]] = None,
        parent_rank: int = 1,
        child_rank: int = 1,
        survived: bool = False,
        generation: int = 0,
    ) -> float:
        """Compute credit and decay-update utility. Returns mutation value."""
        credit = compute_credit(
            parent_objectives,
            child_objectives,
            population_front=population_front,
            parent_rank=parent_rank,
            child_rank=child_rank,
            survived=survived,
            weights=self.config.weights,
            seed=generation,
        )
        self._absorb(mutation_type, credit.mutation_value, credit.to_dict())
        return credit.mutation_value

    def update_record(self, record) -> float:
        """Accept Phase 2 EvolutionRecord (or dict-like with objectives)."""
        parent = list(getattr(record, "parent_objectives", []) or record.get("parent_objectives"))
        child = list(getattr(record, "child_objectives", []) or record.get("child_objectives"))
        mtype = str(getattr(record, "mutation_type", "") or record.get("mutation_type"))
        survived = bool(getattr(record, "survived_next_generation", False))
        rank_change = int(getattr(record, "pareto_rank_change", 0) or 0)
        hv_c = getattr(record, "hypervolume_contribution", None)
        div_c = getattr(record, "diversity_contribution", None)

        # Prefer explicit credit fields when present.
        if hv_c is not None or div_c is not None or survived:
            imp = _imp(parent, child)
            hv_n = math.tanh(max(0.0, float(hv_c or 0.0)) * 10.0)
            div_n = max(0.0, min(2.0, float(div_c or 0.0))) / 2.0
            surv = 1.0 if survived else 0.0
            w = self.config.weights.normalized()
            mv = w.alpha * max(-1.0, min(1.0, imp)) + w.beta * hv_n + w.gamma * div_n + w.delta * surv
            self._absorb(
                mtype,
                mv,
                {
                    "improvement": imp,
                    "hypervolume_gain": float(hv_c or 0.0),
                    "diversity_gain": div_n,
                    "survival_credit": surv,
                    "pareto_rank_change": rank_change,
                },
            )
            # Legacy success-rate view.
            self._legacy.update(record) if hasattr(record, "success") else None
            return float(mv)

        return self.update(
            mtype,
            parent_objectives=parent,
            child_objectives=child,
            survived=survived,
        )

    def update_many(self, records: Iterable) -> None:
        for r in records:
            self.update_record(r)

    def _absorb(self, mutation_type: str, mv: float, components: Dict[str, float]) -> None:
        lam = self.config.decay
        util = self.utility.get(mutation_type)
        if util is None:
            util = MutationUtility(value=self.config.prior_value)
            self.utility[mutation_type] = util
        # score_t = λ * current + (1-λ) * historical
        util.value = lam * float(mv) + (1.0 - lam) * util.value
        util.n_updates += 1
        util.last_mv = float(mv)
        util.components = components
        self.history_mv.setdefault(mutation_type, []).append(float(mv))

    # ------------------------------------------------------------------ #
    # Score / query
    # ------------------------------------------------------------------ #
    def get_score(self, mutation_type: str) -> float:
        """Decayed composite utility, floored for exploration."""
        util = self.utility.get(mutation_type)
        if util is None:
            # Prior + Phase 2 smoothed success as weak fallback.
            base = self.config.prior_value
            return max(self.config.min_score, base + 0.05 * self._legacy.get_score(mutation_type))
        return max(self.config.min_score, util.value)

    def scores(self, mutation_types: Optional[Sequence[str]] = None) -> Dict[str, float]:
        types = list(mutation_types) if mutation_types is not None else sorted(
            set(self.utility) | set(self._legacy.stats)
        )
        return {t: self.get_score(t) for t in types}

    def query(self, mutation_type: str) -> MutationUtility:
        return self.utility.get(mutation_type, MutationUtility(value=self.config.prior_value))

    def ranking(self, mutation_types: Sequence[str]) -> List[Tuple[str, float]]:
        return sorted(((t, self.get_score(t)) for t in mutation_types), key=lambda x: -x[1])

    def summary(self) -> Dict[str, Dict[str, Any]]:
        return {t: u.to_dict() for t, u in sorted(self.utility.items())}

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": {
                "decay": self.config.decay,
                "prior_weight": self.config.prior_weight,
                "prior_value": self.config.prior_value,
                "min_score": self.config.min_score,
                "weights": {
                    "alpha": self.config.weights.alpha,
                    "beta": self.config.weights.beta,
                    "gamma": self.config.weights.gamma,
                    "delta": self.config.weights.delta,
                },
            },
            "utility": {t: u.to_dict() for t, u in self.utility.items()},
            "history_mv": {t: list(v) for t, v in self.history_mv.items()},
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ParetoExperience":
        cfg_d = dict(data.get("config", {}))
        w_d = dict(cfg_d.get("weights", {}))
        cfg = PEEMConfig(
            decay=float(cfg_d.get("decay", 0.35)),
            prior_weight=float(cfg_d.get("prior_weight", 1.5)),
            prior_value=float(cfg_d.get("prior_value", 0.3)),
            min_score=float(cfg_d.get("min_score", 1e-3)),
            weights=CreditWeights(
                alpha=float(w_d.get("alpha", 0.35)),
                beta=float(w_d.get("beta", 0.30)),
                gamma=float(w_d.get("gamma", 0.20)),
                delta=float(w_d.get("delta", 0.15)),
            ),
        )
        exp = cls(cfg)
        for t, u in dict(data.get("utility", {})).items():
            exp.utility[t] = MutationUtility.from_dict(u)
        for t, vals in dict(data.get("history_mv", {})).items():
            exp.history_mv[t] = [float(x) for x in vals]
        return exp

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load_json(cls, path: str | Path) -> "ParetoExperience":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _imp(parent: Sequence[float], child: Sequence[float]) -> float:
    gains = []
    for i, (p, c) in enumerate(zip(parent, child)):
        gains.append((float(p) - float(c)) if i == 2 else (float(c) - float(p)))
    pos = sum(max(0.0, g) for g in gains)
    neg = sum(max(0.0, -g) for g in gains)
    return (pos - 0.5 * neg) / max(1, len(parent))
