"""Run a Phase 0 NSGA-III demo on the toy AgentGenome landscape.

Usage:
    python experiments/run_nsga3_demo.py

Outputs (under results/):
    - population_history.json
    - pareto_front.json
    - objective_scatter.png   (if matplotlib is available)
    - run_summary.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

# Make `src` importable when running as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.evaluator import ToyEvaluator
from src.evaluation.objectives import OBJECTIVE_NAMES, to_minimization
from src.evolution.population import Population, PopulationConfig


RESULTS_DIR = ROOT / "results"


def run_experiment(
    *,
    pop_size: int = 60,
    n_generations: int = 25,
    divisions: int = 3,
    seed: int = 42,
    n_seeds: int = 1,
) -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    evaluator = ToyEvaluator(noise_scale=1.0)

    all_fronts: List[List[List[float]]] = []
    all_histories: List[List[Dict[str, Any]]] = []
    best_front: List[List[float]] = []
    best_front_genomes: List[Dict[str, Any]] = []

    for s in range(n_seeds):
        cfg = PopulationConfig(
            pop_size=pop_size,
            n_offspring=pop_size,
            n_objectives=5,
            divisions=divisions,
            seed=seed + s,
        )
        pop = Population(evaluator=evaluator.evaluate, config=cfg)
        pop.initialize()
        pop.run(n_generations)

        front = pop.pareto_front()
        front_raw = [ind.fitness_vector for ind in front if ind.fitness_vector]
        all_fronts.append(front_raw)
        all_histories.append(list(pop.history))

        # Keep a single representative front file (seed 0 / largest).
        if not best_front or len(front_raw) > len(best_front):
            best_front = front_raw
            best_front_genomes = [
                {
                    "genome": ind.genome.to_dict(),
                    "fitness_vector": ind.fitness_vector,
                    "generation": ind.generation,
                }
                for ind in front
            ]

    history_path = RESULTS_DIR / "population_history.json"
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "n_seeds": n_seeds,
                "pop_size": pop_size,
                "n_generations": n_generations,
                "divisions": divisions,
                "objective_names": list(OBJECTIVE_NAMES),
                "histories": all_histories,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    pareto_path = RESULTS_DIR / "pareto_front.json"
    with pareto_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "objective_names": list(OBJECTIVE_NAMES),
                "n_points": len(best_front),
                "points": best_front_genomes,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    summary = {
        "pop_size": pop_size,
        "n_generations": n_generations,
        "n_seeds": n_seeds,
        "divisions": divisions,
        "seed": seed,
        "pareto_size": len(best_front),
        "objective_names": list(OBJECTIVE_NAMES),
        "generation_history_path": str(history_path),
        "pareto_front_path": str(pareto_path),
    }

    # Optional visualization (best-effort; not a hard requirement if matplotlib missing).
    viz_path = _maybe_plot(best_front, pop_size, n_generations)
    if viz_path is not None:
        summary["objective_viz_path"] = str(viz_path)

    summary_path = RESULTS_DIR / "run_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


def _maybe_plot(front: List[List[float]], pop_size: int, n_generations: int):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        # Write a lightweight textual visualization fallback.
        txt_path = RESULTS_DIR / "objective_viz.txt"
        with txt_path.open("w", encoding="utf-8") as f:
            f.write("Pareto front (raw objectives)\n")
            f.write("index\t" + "\t".join(OBJECTIVE_NAMES) + "\n")
            for i, row in enumerate(front):
                f.write(f"{i}\t" + "\t".join(f"{v:.4f}" for v in row) + "\n")
        return txt_path

    import numpy as np  # optional

    m = len(OBJECTIVE_NAMES)
    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    pairs = [(0, 1), (0, 2), (0, 3), (0, 4)]
    for ax, (i, j) in zip(axes.ravel(), pairs):
        xs = [p[i] for p in front]
        ys = [p[j] for p in front]
        ax.scatter(xs, ys, s=28, alpha=0.8, c="#2b6cb0", edgecolors="white")
        ax.set_xlabel(OBJECTIVE_NAMES[i])
        ax.set_ylabel(OBJECTIVE_NAMES[j])
        ax.set_title(f"{OBJECTIVE_NAMES[i]} vs {OBJECTIVE_NAMES[j]}")
        ax.grid(True, alpha=0.25)

    fig.suptitle(
        f"NSGA-III Pareto front (toy AgentGenome) — pop={pop_size}, gens={n_generations}",
        fontsize=12,
    )
    fig.tight_layout()
    png_path = RESULTS_DIR / "objective_scatter.png"
    fig.savefig(png_path, dpi=140)
    plt.close(fig)
    return png_path


def main() -> None:
    summary = run_experiment()
    print("Phase 0 NSGA-III demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
