"""Phase5-Audit-4: Genotype evolution analysis.

Outputs genotype frequency, mutation trajectory, lineage, Pareto evolution.
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.operator_attribution import observational_operator_stats
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "audit"


def genotype_label(g: AgentGenome) -> str:
    return (
        f"{g.planner_strategy}|{g.memory_strategy}|"
        f"{g.reflection_strategy}|{g.tool_policy}|b{g.reasoning_budget}"
    )


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    pipe = RealLLMPipeline(RealLLMConfig(n_tasks=8, backend="mock", seed=21))
    cfg = MemoryEvolutionConfig(
        pop_size=16, n_offspring=16, seed=21,
        use_adaptive=True, experience_mode="robust_peem",
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()

    freq_by_gen = []
    mutation_by_gen = []
    front_by_gen = []

    def snapshot(gen: int) -> None:
        labels = [genotype_label(i.genome) for i in loop.individuals]
        freq = Counter(labels)
        total = sum(freq.values()) or 1
        ent = -sum((c / total) * math.log2(c / total) for c in freq.values())
        freq_by_gen.append({
            "generation": gen,
            "unique_genotypes": len(freq),
            "entropy": ent,
            "top": freq.most_common(5),
        })
        mutation_by_gen.append({
            "generation": gen,
            "mutation_counts": loop.mutation_type_counts(),
        })
        front = loop.pareto_front()
        front_by_gen.append({
            "generation": gen,
            "n_front": len(front),
            "front_genotypes": [genotype_label(i.genome) for i in front],
            "front_performance": [
                i.fitness_vector[0] for i in front if i.fitness_vector
            ],
        })

    snapshot(0)
    for g in range(1, 7):
        loop.next_generation()
        snapshot(g)

    lineage = []
    for rec in loop.archive.records:
        lineage.append({
            "mutation_type": rec.mutation_type,
            "generation": rec.generation,
            "success": rec.success,
            "mutation_value": rec.mutation_value,
        })
    op_stats = {
        k: v.to_dict()
        for k, v in observational_operator_stats(loop.archive.records).items()
    }

    payload = {
        "phase": "Phase5-Audit-4 genotype evolution",
        "note": (
            "Search is over behavioral genotype "
            "planner/memory/reflection/tool/budget, not a single scalar."
        ),
        "genotype_frequency": freq_by_gen,
        "mutation_trajectory": mutation_by_gen,
        "pareto_front_evolution": front_by_gen,
        "operator_stats": op_stats,
        "lineage_records_sample": lineage[:50],
        "figure": {
            "fig_genotype": "unique_genotypes and entropy vs generation",
            "fig_mutation": "operator counts vs generation",
            "fig_front": "front size and performance range vs generation",
        },
    }
    path = OUT / "genotype_evolution.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "entropy": [f["entropy"] for f in freq_by_gen],
        "unique": [f["unique_genotypes"] for f in freq_by_gen],
        "front": [f["n_front"] for f in front_by_gen],
    }, indent=2))
    return payload


if __name__ == "__main__":
    main()
