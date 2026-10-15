"""Offline PEEM / PPEC mechanism audit (Phase5-R3-R5 Stage C)."""

from __future__ import annotations

import random
from typing import Any, Dict, List

from src.agent.genome import AgentGenome
from src.evolution.adaptive_mutation import AdaptiveMutationController, default_registry
from src.evolution.pareto_experience import PEEMConfig, ParetoExperience
from src.evolution.preference import encode_preference
from src.evolution.preference_controller import PreferenceController


def synthetic_fitness(g: AgentGenome) -> List[float]:
    """Two-objective toy: success-like vs cost-like from genome knobs."""
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    success = p[g.planner_strategy] + 0.1 * (g.reasoning_budget - 8) / 120.0
    cost = 0.2 + 0.6 * (g.reasoning_budget / 128.0) + (
        0.2 if g.tool_policy == "tool_first" else 0.0
    )
    return [success, cost]


def peem_updates_with_native_fit() -> Dict[str, Any]:
    exp = ParetoExperience(PEEMConfig(decay=0.5))
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry())
    rng = random.Random(0)
    parent = AgentGenome.random(rng)
    before = ctrl.probability_distribution()
    # feed a high-MV record for planner
    exp.update(
        "planner",
        parent_objectives=[0.5, 0.5, 0.5, 0.5, 0.5],
        child_objectives=[0.9, 0.5, 0.1, 0.5, 0.5],
        survived=True,
    )
    after = ctrl.probability_distribution()
    return {
        "prob_before_planner": before.get("planner"),
        "prob_after_planner": after.get("planner"),
        "changed": before != after,
    }


def ppec_selection_diff() -> Dict[str, Any]:
    from src.agent.individual import Individual

    a = Individual(genome=AgentGenome.random(random.Random(1)), fitness_vector=[0.9, 0.05], generation=0)
    b = Individual(genome=AgentGenome.random(random.Random(2)), fitness_vector=[0.5, 0.01], generation=0)
    ctrl_acc = PreferenceController(preference=encode_preference("accuracy_first"))
    ctrl_cost = PreferenceController(preference=encode_preference("cost_first"))
    # score via preference_satisfaction on 2-obj is not native; use full 5-obj pads
    a5 = Individual(genome=a.genome, fitness_vector=[0.9, 0.5, 0.1, 0.5, 0.5], generation=0)
    b5 = Individual(genome=b.genome, fitness_vector=[0.5, 0.5, 0.5, 0.5, 0.5], generation=0)
    ra = ctrl_acc.score_individual(a5)
    rb = ctrl_acc.score_individual(b5)
    rc = ctrl_cost.score_individual(a5)
    rd = ctrl_cost.score_individual(b5)
    return {
        "accuracy_prefers_a": ra >= rb,
        "cost_prefers_b": rd >= rc,
        "selection_differs": (ra >= rb) != (rd >= rc),
    }


def ppec_reference_directions_differ() -> Dict[str, Any]:
    c1 = PreferenceController(preference=encode_preference("accuracy_first"))
    c2 = PreferenceController(preference=encode_preference("cost_first"))
    d1 = c1.get_reference_region()["directions"]
    d2 = c2.get_reference_region()["directions"]
    return {"directions_differ": d1 != d2, "n": len(d1)}


def all_zero_success_bias_check() -> Dict[str, Any]:
    """If all offspring fail, PEEM should not lock to cheapest-fail only."""
    exp = ParetoExperience(PEEMConfig(decay=0.3))
    for i in range(10):
        exp.update(
            "budget",
            parent_objectives=[0.2, 0.5, 0.5, 0.5, 0.5],
            child_objectives=[0.2, 0.5, 0.2, 0.5, 0.5],
            survived=False,
        )
        exp.update(
            "planner",
            parent_objectives=[0.2, 0.5, 0.5, 0.5, 0.5],
            child_objectives=[0.2, 0.5, 0.5, 0.5, 0.5],
            survived=False,
        )
    return {
        "budget_score": exp.get_score("budget"),
        "planner_score": exp.get_score("planner"),
        "budget_not_dominant": exp.get_score("budget") <= exp.get_score("planner") + 1.0,
    }


def run_audit() -> Dict[str, Any]:
    return {
        "peem_mechanism": peem_updates_with_native_fit(),
        "ppec_selection": ppec_selection_diff(),
        "ppec_refs": ppec_reference_directions_differ(),
        "all_zero_bias": all_zero_success_bias_check(),
        "ablation_note": "RS vs NSGA-III vs +PEEM vs +PEEM+PPEC must be separately attributable",
    }
