"""Phase5-Audit-2: PEEM credit attribution analysis.

Observational archive stats vs counterfactual mutation intervention.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.operator_attribution import (
    attribution_verdict,
    counterfactual_probe,
    observational_operator_stats,
)
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline

OUT = ROOT / "results" / "audit"


def toy_eval(genome: AgentGenome):
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    e = {"direct": 0.9, "cot": 0.7, "plan_and_solve": 0.55, "tree_search": 0.35, "reflexion": 0.45}
    c = {"no_tools": 0.1, "conservative": 0.3, "balanced": 0.45, "aggressive": 0.7, "tool_first": 0.85}
    t = (genome.reasoning_budget - 8) / 120.0
    return [
        p[genome.planner_strategy] + 0.05 * t,
        e[genome.planner_strategy] - 0.2 * t,
        c[genome.tool_policy] + 0.3 * t,
        0.5 + 0.3 * p[genome.planner_strategy],
        0.5 + 0.2 * e[genome.planner_strategy],
    ]


def main() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) Collect observational records from a PEEM run.
    pipe = RealLLMPipeline(RealLLMConfig(n_tasks=6, backend="mock", seed=7))
    cfg = MemoryEvolutionConfig(pop_size=12, n_offspring=12, seed=7, use_adaptive=True,
                                experience_mode="robust_peem")
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    loop.run(6)
    obs = observational_operator_stats(loop.archive.records)
    obs_summary = {k: v.to_dict() for k, v in obs.items()}
    # Bootstrap CIs already in stats.
    print("OBSERVATIONAL", json.dumps(obs_summary, indent=2)[:1500])

    # 2) Counterfactual probe on random parents from the genome space.
    rng = random.Random(11)
    parents = [AgentGenome.random(rng) for _ in range(20)]
    cf = counterfactual_probe(parents, toy_eval, seed=11, n_repeats=3)
    cf_summary = {k: v.to_dict() for k, v in cf.items()}
    print("COUNTERFACTUAL", json.dumps(cf_summary, indent=2)[:1500])

    # 3) Verdict
    verdict = attribution_verdict(obs, cf)
    print("VERDICT", json.dumps(verdict, indent=2))

    payload = {
        "phase": "Phase5-Audit-2 PEEM credit attribution",
        "question": "Does PEEM learn causal operator contribution or correlate with successful offspring?",
        "observational": obs_summary,
        "counterfactual": cf_summary,
        "verdict": verdict,
        "limitations": [
            "Observational MV mixes improvement, pareto bucket, diversity, survival — inherently correlational with offspring outcome.",
            "Counterfactual probe uses do-intervention on mutation type but a toy evaluator and n=20 parents.",
            "Confidence intervals are percentile bootstrap on per-transition improvement (not on full MV).",
            "We do NOT claim full causal identification; PEEM is a credit-assignment heuristic.",
        ],
    }
    (OUT / "credit_attribution.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    main()
