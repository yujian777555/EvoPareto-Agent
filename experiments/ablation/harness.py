"""Shared ablation harness (Phase 5-Pre).

No algorithm changes — experiment configuration, metrics, and reporting only.
Uses the MockLLMBackend + ALFWorld-style adapter for reproducible multi-seed
statistics; real-LLM confirmation lives in Phase 4-R2 artifacts.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    import sys

    sys.path.insert(0, str(ROOT))

from src.evaluation.metrics import (
    hypervolume,
    igd,
    mutation_entropy,
    preference_satisfaction_score,
    reference_front_from_population,
)
from src.evolution.credit_assignment import CreditWeights
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.preference import encode_preference
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

RESULTS = ROOT / "results" / "ablation"

# Fixed paper-style config for all framework ablations (3 seeds).
ABLATION_CONFIG = {
    "pop": 16,
    "gens": 8,
    "tasks": 8,
    "seeds": [11, 22, 33],
    "budget_evals": 16 + 16 * 8,  # 144 genome evaluations
}


@dataclass
class AblationResult:
    name: str
    seed: int
    metrics: Dict[str, float]
    history: List[Dict[str, Any]] = field(default_factory=list)
    wall_time: float = 0.0
    front_rows: List[List[float]] = field(default_factory=list)
    population_rows: List[List[float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "seed": self.seed,
            "metrics": dict(self.metrics),
            "history": self.history,
            "wall_time": self.wall_time,
        }


def ms(vals: Sequence[float]) -> Dict[str, float]:
    n = len(vals)
    if n == 0:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / n
    var = sum((x - m) ** 2 for x in vals) / n
    return {"mean": m, "std": var ** 0.5}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def run_variant(
    name: str,
    *,
    seed: int,
    use_adaptive: bool = True,
    experience_mode: str = "robust_peem",
    preference: Any = None,
    use_softmax: bool = True,
    use_delayed: bool = True,
    credit_weights: Optional[CreditWeights] = None,
    pop: int = 16,
    gens: int = 8,
    tasks: int = 8,
    track_curve: bool = False,
) -> AblationResult:
    """One controlled evolution run under the mock-LLM benchmark."""
    t0 = time.time()
    pipe = RealLLMPipeline(
        RealLLMConfig(n_tasks=tasks, backend="mock", seed=seed),
        cache=None,  # no cache: every evaluation counts (budget fairness)
    )
    cfg = MemoryEvolutionConfig(
        pop_size=pop,
        n_offspring=pop,
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=experience_mode,
        preference=preference,
        use_softmax=use_softmax,
        use_delayed_credit=use_delayed,
        credit_weights=credit_weights,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    if track_curve:
        curve = [dict(h) for h in loop.history]
        for _ in range(gens):
            loop.next_generation()
            curve.append(dict(loop.history[-1]))
    else:
        loop.run(gens)
        curve = list(loop.history)

    front = loop.pareto_front()
    ff = [list(i.fitness_vector or []) for i in front]
    rows = [list(i.fitness_vector or []) for i in loop.individuals]
    # IGD vs this run's front is trivially 0; store rows for a later
    # cross-method reference. Placeholder IGD filled by finalize_igd().
    pref = encode_preference(preference) if preference is not None else encode_preference("balanced")
    counts = list(loop.mutation_type_counts().values())

    metrics = {
        "hypervolume": float(hypervolume(rows, n_samples=512, seed=seed)),
        "igd": 0.0,  # replaced in finalize_igd
        "success": float(sum(r[0] for r in rows) / len(rows)) if rows else 0.0,
        "cost": float(sum(r[2] for r in rows) / len(rows)) if rows else 0.0,
        "efficiency": float(sum(r[1] for r in rows) / len(rows)) if rows else 0.0,
        "pss": float(preference_satisfaction_score(rows, pref)) if rows else 0.0,
        "mutation_entropy": float(mutation_entropy(counts)) if counts else 0.0,
        "n_non_dominated": float(len(ff)),
        "evaluations": float(pop * (gens + 1)),
    }
    return AblationResult(
        name=name,
        seed=seed,
        metrics=metrics,
        history=curve if track_curve else [],
        wall_time=time.time() - t0,
        front_rows=ff,
        population_rows=rows,
    )


def finalize_igd(runs: List[AblationResult], all_rows: List[List[float]]) -> None:
    """Fill IGD using a shared reference front (union of all runs' populations)."""
    if not all_rows:
        return
    ref = reference_front_from_population(all_rows)
    # Need each run's front rows; re-derive from stored history is lossy.
    # Instead compute IGD of each run's *final non-dominated set* if present
    # in metrics, else leave 0. We stash front rows on the result object.
    for r in runs:
        front = getattr(r, "front_rows", None)
        if front:
            r.metrics["igd"] = float(igd(front, ref))


def aggregate(runs: List[AblationResult], keys: Sequence[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in sorted({r.name for r in runs}):
        sub = [r for r in runs if r.name == name]
        out[name] = {k: ms([r.metrics.get(k, 0.0) for r in sub]) for k in keys}
        out[name]["n_seeds"] = len(sub)
    return out


def seed_reproducible(
    name: str,
    run_fn: Callable[[], AblationResult],
    *,
    n_repeat: int = 2,
) -> bool:
    """Check that the same seed yields identical metrics."""
    metrics = []
    for _ in range(n_repeat):
        metrics.append(run_fn().metrics)
    return metrics[0] == metrics[1]
