"""Operator utility time-series logging (Phase5-R2).

Non-invasive: wraps MemoryEvolutionLoop.next_generation and snapshots
per-operator statistics. **Does not change PEEM / NSGA-III / PPEC logic.**
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from src.evolution.memory_evolution import MemoryEvolutionLoop

OPERATORS = ("planner", "memory", "reflection", "tool", "budget")


@dataclass
class OperatorSnapshot:
    generation: int
    operators: Dict[str, Dict[str, float]]
    global_metrics: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "generation": self.generation,
            "operators": self.operators,
            "global_metrics": self.global_metrics,
        }


class OperatorUtilityLogger:
    """Collects per-generation operator utility / probability / usage stats."""

    def __init__(self, benchmark: str = "", seed: int = 0) -> None:
        self.benchmark = benchmark
        self.seed = seed
        self.snapshots: List[OperatorSnapshot] = []
        self._last_log_len = 0

    def snapshot(self, loop: MemoryEvolutionLoop) -> OperatorSnapshot:
        gen = loop.generation
        # Usage this generation (from mutation_log tail).
        new_logs = loop.mutation_log[self._last_log_len :]
        self._last_log_len = len(loop.mutation_log)
        counts = {op: 0.0 for op in OPERATORS}
        for name in new_logs:
            for op in OPERATORS:
                if op in name:
                    counts[op] += 1.0
                    break

        # Archive records for this generation.
        recs = [r for r in loop.archive.records if r.generation == gen]
        accepted = {op: 0.0 for op in OPERATORS}
        credit_sum = {op: 0.0 for op in OPERATORS}
        credit_n = {op: 0.0 for op in OPERATORS}
        surv_num = {op: 0.0 for op in OPERATORS}
        surv_n = {op: 0.0 for op in OPERATORS}
        for r in recs:
            for op in OPERATORS:
                if op in r.mutation_type:
                    credit_sum[op] += float(getattr(r, "mutation_value", 0.0))
                    credit_n[op] += 1.0
                    if getattr(r, "survived_next_generation", False):
                        accepted[op] += 1.0
                        surv_num[op] += 1.0
                    surv_n[op] += 1.0
                    break

        probs = {}
        try:
            probs = loop.controller.probability_distribution()
        except Exception:
            probs = {op: 0.0 for op in OPERATORS}

        operators = {}
        for op in OPERATORS:
            n = counts.get(op, 0.0)
            cn = credit_n.get(op, 0.0)
            sn = surv_n.get(op, 0.0)
            utility = 0.0
            if hasattr(loop.experience, "get_score"):
                try:
                    utility = float(loop.experience.get_score(op))
                except Exception:
                    utility = 0.0
            operators[op] = {
                "utility": utility,
                "probability": float(probs.get(op, 0.0)),
                "count": n,
                "accepted": accepted.get(op, 0.0),
                "avg_credit": (credit_sum[op] / cn) if cn else 0.0,
                "survival_rate": (surv_num[op] / sn) if sn else 0.0,
            }

        rows = [list(i.fitness_vector or []) for i in loop.individuals]
        gm = {
            "hypervolume": float(loop.history[-1].get("hypervolume", 0.0)) if loop.history else 0.0,
            "mean_performance": sum(r[0] for r in rows) / len(rows) if rows else 0.0,
            "mean_cost": sum(r[2] for r in rows) / len(rows) if rows else 0.0,
        }
        snap = OperatorSnapshot(generation=gen, operators=operators, global_metrics=gm)
        self.snapshots.append(snap)
        return snap

    def to_dict(self) -> dict:
        return {
            "benchmark": self.benchmark,
            "seed": self.seed,
            "operators": list(OPERATORS),
            "generations": [s.to_dict() for s in self.snapshots],
        }

    def save_json(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


class LoggingLoop(MemoryEvolutionLoop):
    """MemoryEvolutionLoop + automatic operator utility snapshots."""

    logger: OperatorUtilityLogger

    def __post_init__(self) -> None:
        super().__post_init__()
        self.logger = OperatorUtilityLogger()

    def next_generation(self):
        out = super().next_generation()
        self.logger.snapshot(self)
        return out

    def initialize(self, genomes=None):
        out = super().initialize(genomes)
        self.logger.snapshot(self)
        return out


def aggregate_seed_timeseries(
    runs: Sequence[dict],
) -> Dict[str, Any]:
    """Mean/std of utility & probability per operator per generation."""
    if not runs:
        return {}
    # runs: list of logger.to_dict()
    gens = [g["generation"] for g in runs[0]["generations"]]
    out = {"generation": gens, "operators": {}}
    for op in OPERATORS:
        util_series = []
        prob_series = []
        count_series = []
        accept_series = []
        credit_series = []
        for run in runs:
            u, p, c, a, cr = [], [], [], [], []
            for g in run["generations"]:
                opd = g["operators"][op]
                u.append(opd["utility"])
                p.append(opd["probability"])
                c.append(opd["count"])
                a.append(opd["accepted"])
                cr.append(opd["avg_credit"])
            util_series.append(u)
            prob_series.append(p)
            count_series.append(c)
            accept_series.append(a)
            credit_series.append(cr)

        def ms(series):
            n = len(series[0])
            mean, std = [], []
            for i in range(n):
                vals = [s[i] for s in series]
                m = sum(vals) / len(vals)
                var = sum((v - m) ** 2 for v in vals) / len(vals)
                mean.append(m)
                std.append(var ** 0.5)
            return mean, std

        um, us = ms(util_series)
        pm, ps = ms(prob_series)
        cm, cs = ms(count_series)
        am, as_ = ms(accept_series)
        crm, crs = ms(credit_series)
        out["operators"][op] = {
            "utility_mean": um, "utility_std": us,
            "probability_mean": pm, "probability_std": ps,
            "count_mean": cm, "count_std": cs,
            "accepted_mean": am, "accepted_std": as_,
            "avg_credit_mean": crm, "avg_credit_std": crs,
        }
    return out
