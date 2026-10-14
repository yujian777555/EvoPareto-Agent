"""Phase 1 demo: evolve real (mock-backed) agent genomes with NSGA-III.

Usage:
    python experiments/run_agent_evolution_demo.py

Outputs (under results/):
    - agent_population_history.json
    - agent_pareto_front.json
    - agent_evolution_summary.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.objectives import OBJECTIVE_NAMES
from src.runtime.pipeline import run_agent_evolution

RESULTS_DIR = ROOT / "results"


def main() -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    pop_size = 30
    n_generations = 10
    n_tasks = 12
    seed = 42

    out = run_agent_evolution(
        pop_size=pop_size,
        n_generations=n_generations,
        n_tasks=n_tasks,
        seed=seed,
    )
    pop = out["population"]
    front = out["front"]

    history_path = RESULTS_DIR / "agent_population_history.json"
    with history_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "pop_size": pop_size,
                "n_generations": n_generations,
                "n_tasks": n_tasks,
                "seed": seed,
                "objective_names": list(OBJECTIVE_NAMES),
                "history": out["history"],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    pareto_path = RESULTS_DIR / "agent_pareto_front.json"
    points = [
        {
            "genome": ind.genome.to_dict(),
            "fitness_vector": ind.fitness_vector,
            "generation": ind.generation,
        }
        for ind in front
    ]
    with pareto_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "objective_names": list(OBJECTIVE_NAMES),
                "n_points": len(points),
                "points": points,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    summary = {
        "phase": "Phase 1 — agent runtime evaluation foundation",
        "pop_size": pop_size,
        "n_generations": n_generations,
        "n_tasks": n_tasks,
        "seed": seed,
        "pareto_size": len(points),
        "objective_names": list(OBJECTIVE_NAMES),
        "history_path": str(history_path),
        "pareto_front_path": str(pareto_path),
        "note": "MockBenchmark behavioral model; no commercial LLM API.",
    }
    summary_path = RESULTS_DIR / "agent_evolution_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("Phase 1 agent-evolution demo complete.")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


if __name__ == "__main__":
    main()
