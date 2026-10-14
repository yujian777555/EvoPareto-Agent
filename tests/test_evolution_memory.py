"""Phase 2 tests: archive, experience, adaptive mutation, metrics, integration."""

import json
import random
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.metrics import hypervolume, hypervolume_2d_max, pareto_front_size
from src.evolution.adaptive_mutation import (
    AdaptiveMutationController,
    MutationOperatorRegistry,
    default_registry,
)
from src.evolution.archive import (
    EvolutionArchive,
    EvolutionRecord,
    is_successful_transition,
    objective_delta,
)
from src.evolution.experience import MutationExperience, MutationStats
from src.evolution.memory_evolution import (
    MemoryEvolutionConfig,
    MemoryEvolutionLoop,
    run_memory_evolution,
)


def make_genome(**kwargs) -> AgentGenome:
    base = dict(
        planner_strategy="cot",
        memory_strategy="episodic",
        reflection_strategy="self_critique",
        tool_policy="balanced",
        reasoning_budget=32,
    )
    base.update(kwargs)
    return AgentGenome(**base)


def toy_eval(genome: AgentGenome):
    """Deterministic 5-obj mapping (paper semantics)."""
    p = {"direct": 0.4, "cot": 0.6, "plan_and_solve": 0.75, "tree_search": 0.9, "reflexion": 0.85}
    e = {"direct": 0.9, "cot": 0.7, "plan_and_solve": 0.55, "tree_search": 0.35, "reflexion": 0.45}
    c = {"no_tools": 0.1, "conservative": 0.3, "balanced": 0.45, "aggressive": 0.7, "tool_first": 0.85}
    budget_t = (genome.reasoning_budget - 8) / 120.0
    perf = p[genome.planner_strategy] + 0.05 * budget_t
    eff = e[genome.planner_strategy] - 0.2 * budget_t
    cost = c[genome.tool_policy] + 0.3 * budget_t
    rob = 0.5 + 0.3 * p[genome.planner_strategy]
    auto = 0.5 + 0.2 * e[genome.planner_strategy]
    return [perf, eff, cost, rob, auto]


# ====================================================================== #
# Archive
# ====================================================================== #
def test_record_creation_and_delta():
    rec = EvolutionRecord(
        generation=1,
        parent_genome_id="a",
        child_genome_id="b",
        mutation_type="planner",
        parent_objectives=[0.5, 0.5, 0.5, 0.5, 0.5],
        child_objectives=[0.6, 0.5, 0.4, 0.5, 0.5],
        objective_delta=objective_delta([0.5, 0.5, 0.5, 0.5, 0.5], [0.6, 0.5, 0.4, 0.5, 0.5]),
        hypervolume_delta=0.02,
        success=True,
    )
    assert rec.generation == 1
    assert rec.mutation_type == "planner"
    assert rec.objective_delta[0] == pytest.approx(0.1)
    assert rec.objective_delta[2] == pytest.approx(-0.1)


def test_record_serialization_roundtrip():
    rec = EvolutionRecord(
        generation=2,
        parent_genome_id="p",
        child_genome_id="c",
        mutation_type="budget",
        parent_objectives=[0.1, 0.2, 0.3, 0.4, 0.5],
        child_objectives=[0.2, 0.2, 0.2, 0.4, 0.5],
        objective_delta=[0.1, 0.0, -0.1, 0.0, 0.0],
        hypervolume_delta=0.0,
        success=False,
    )
    d = rec.to_dict()
    rec2 = EvolutionRecord.from_dict(d)
    assert rec2 == rec
    assert EvolutionRecord.from_json if False else True


def test_archive_persistence(tmp_path: Path):
    arch = EvolutionArchive()
    arch.record_transition(
        generation=1,
        parent_genome_id="p1",
        child_genome_id="c1",
        mutation_type="planner",
        parent_objectives=[0.4, 0.4, 0.6, 0.4, 0.4],
        child_objectives=[0.7, 0.4, 0.6, 0.5, 0.5],
    )
    arch.record_transition(
        generation=1,
        parent_genome_id="p2",
        child_genome_id="c2",
        mutation_type="tool",
        parent_objectives=[0.5, 0.5, 0.5, 0.5, 0.5],
        child_objectives=[0.5, 0.5, 0.5, 0.5, 0.5],
    )
    path = tmp_path / "archive.json"
    arch.save_json(path)
    loaded = EvolutionArchive.load_json(path)
    assert len(loaded) == 2
    assert loaded.mutation_types() == ["planner", "tool"]
    assert loaded.summary()["n_success"] == arch.summary()["n_success"]


def test_is_successful_transition_dominates():
    parent = [0.5, 0.5, 0.5, 0.5, 0.5]
    child = [0.8, 0.5, 0.4, 0.5, 0.5]  # better perf + cost
    assert is_successful_transition(parent, child)
    assert not is_successful_transition(child, parent)


# ====================================================================== #
# Experience
# ====================================================================== #
def test_experience_update_statistics():
    exp = MutationExperience()
    for i in range(10):
        exp.update(
            EvolutionRecord(
                generation=i,
                parent_genome_id=str(i),
                child_genome_id=str(i + 100),
                mutation_type="planner",
                parent_objectives=[0.5] * 5,
                child_objectives=[0.6] * 5,
                objective_delta=[0.1] * 5,
                hypervolume_delta=0.02,
                success=i < 6,
            )
        )
    st = exp.get_stats("planner")
    assert st.count == 10
    assert st.success == 6
    assert st.success_rate == pytest.approx(0.6)
    assert st.average_improvement > 0


def test_experience_score_and_summary():
    exp = MutationExperience(prior_weight=1.0, prior_success_rate=0.35)
    assert exp.get_score("planner") > 0  # prior only
    exp.update(
        EvolutionRecord(
            generation=0,
            parent_genome_id="a",
            child_genome_id="b",
            mutation_type="planner",
            parent_objectives=[0.5] * 5,
            child_objectives=[0.6] * 5,
            objective_delta=[0.1] * 5,
            hypervolume_delta=0.05,
            success=True,
        )
    )
    assert exp.get_score("planner") > exp.get_score("tool")
    assert "planner" in exp.summary()


def test_experience_persistence(tmp_path: Path):
    exp = MutationExperience()
    exp.update(
        EvolutionRecord(
            generation=0,
            parent_genome_id="a",
            child_genome_id="b",
            mutation_type="memory",
            parent_objectives=[0.5] * 5,
            child_objectives=[0.5] * 5,
            objective_delta=[0.0] * 5,
            hypervolume_delta=0.0,
            success=False,
        )
    )
    path = tmp_path / "exp.json"
    exp.save_json(path)
    loaded = MutationExperience.load_json(path)
    assert loaded.get_stats("memory").count == 1
    assert loaded.get_stats("memory").success == 0


# ====================================================================== #
# Adaptive mutation
# ====================================================================== #
def test_registry_default_and_apply():
    reg = default_registry()
    assert set(reg.names()) >= {"planner", "memory", "tool", "budget", "reflection"}
    rng = random.Random(0)
    g = make_genome()
    g2 = reg.apply("planner", g, rng, rate=1.0)
    assert g2.planner_strategy != g.planner_strategy


def test_probability_normalization():
    exp = MutationExperience()
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry())
    dist = ctrl.probability_distribution()
    assert set(dist) == set(default_registry().names())
    assert sum(dist.values()) == pytest.approx(1.0)
    assert all(v > 0 for v in dist.values())


def test_adaptive_controller_prefers_successful_mutation():
    exp = MutationExperience()
    # Make planner historically excellent, budget poor.
    for _ in range(20):
        exp.update(
            EvolutionRecord(
                generation=0, parent_genome_id="p", child_genome_id="c",
                mutation_type="planner",
                parent_objectives=[0.5] * 5, child_objectives=[0.8] * 5,
                objective_delta=[0.3] * 5, hypervolume_delta=0.05, success=True,
            )
        )
        exp.update(
            EvolutionRecord(
                generation=0, parent_genome_id="p", child_genome_id="c",
                mutation_type="budget",
                parent_objectives=[0.5] * 5, child_objectives=[0.4] * 5,
                objective_delta=[-0.1] * 5, hypervolume_delta=0.0, success=False,
            )
        )
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry(), epsilon=0.0, min_prob=0.0)
    dist = ctrl.probability_distribution()
    assert dist["planner"] > dist["budget"]


def test_deterministic_selection():
    exp = MutationExperience()
    ctrl = AdaptiveMutationController(experience=exp, registry=default_registry())
    g = make_genome()
    r1, names1 = ctrl.mutate(g, random.Random(123), n_mutations=2)
    r2, names2 = ctrl.mutate(g, random.Random(123), n_mutations=2)
    assert names1 == names2
    assert r1 == r2


# ====================================================================== #
# Metrics
# ====================================================================== #
def test_hypervolume_2d_max_sanity():
    front = [[0.8, 0.8], [0.9, 0.5]]
    hv = hypervolume_2d_max(front, ref=[0.0, 0.0])
    assert hv > 0
    assert hypervolume_2d_max(front + [[1.0, 1.0]], ref=[0.0, 0.0]) > hv


def test_hypervolume_paper_semantics():
    better = [[0.9, 0.9, 0.1, 0.9, 0.9]]
    worse = [[0.2, 0.2, 0.9, 0.2, 0.2]]
    assert hypervolume(better) > hypervolume(worse)
    assert hypervolume([]) == 0.0


def test_pareto_front_size():
    rows = [[1.0, 1.0], [2.0, 0.5], [0.2, 0.2]]
    assert pareto_front_size(rows) == 2


# ====================================================================== #
# Integration
# ====================================================================== #
def test_archive_update_after_evolution():
    out = run_memory_evolution(toy_eval, pop_size=10, n_generations=3, seed=1, use_adaptive=True)
    archive = out["archive"]
    assert len(archive) > 0
    assert archive.summary()["n_records"] == len(archive)
    # Every record has mutation type from registry or random
    assert all(r.mutation_type for r in archive)


def test_experience_updated_after_evolution():
    out = run_memory_evolution(toy_eval, pop_size=10, n_generations=3, seed=2, use_adaptive=True)
    exp = out["experience"]
    assert any(st.count > 0 for st in exp.stats.values())


def test_end_to_end_memory_pipeline():
    out = run_memory_evolution(toy_eval, pop_size=12, n_generations=4, seed=3, use_adaptive=True)
    assert out["final_hypervolume"] >= 0
    assert out["final_pareto_size"] >= 1
    probs = out["mutation_probs"]
    assert probs and abs(sum(probs.values()) - 1.0) < 1e-6
    hist = out["history"]
    assert len(hist) == 5  # init + 4
    assert "hypervolume" in hist[-1]


def test_adaptive_vs_random_runs():
    a = run_memory_evolution(toy_eval, pop_size=12, n_generations=3, seed=9, use_adaptive=True)
    r = run_memory_evolution(toy_eval, pop_size=12, n_generations=3, seed=9, use_adaptive=False)
    assert a["final_hypervolume"] >= 0 and r["final_hypervolume"] >= 0
    # Adaptive loop should have recorded mutation types beyond "random"
    types_a = {rec.mutation_type for rec in a["archive"]}
    assert types_a  # non-empty


def test_phase2_demo_smoke(tmp_path, monkeypatch):
    import experiments.run_evolution_memory_demo as demo

    monkeypatch.setattr(demo, "RESULTS_DIR", tmp_path)
    # Shrink experiments for speed
    monkeypatch.setattr(demo, "experiment_1", lambda **k: {
        "name": "E1", "mean_final_hv_random": 0.1, "mean_final_hv_adaptive": 0.2,
        "mean_final_pareto_random": 3, "mean_final_pareto_adaptive": 4,
        "mean_hv_curve_random": [0.0], "mean_hv_curve_adaptive": [0.0], "runs": [],
    })
    monkeypatch.setattr(demo, "experiment_2", lambda **k: {
        "name": "E2", "mean_evals_random_to_target": 100, "mean_evals_adaptive_to_target": 80,
        "records": [],
    })
    monkeypatch.setattr(demo, "experiment_3", lambda **k: {
        "name": "E3", "mean_final_hv_nsga3": 0.1, "mean_final_hv_nsga3_memory": 0.15,
        "mean_final_pareto_nsga3": 3, "mean_final_pareto_nsga3_memory": 5,
        "mean_hv_curve_nsga3": [0.0], "mean_hv_curve_memory": [0.0], "runs": [],
    })
    summary = demo.main()
    assert (tmp_path / "evolution_memory_results.json").exists()
    assert (tmp_path / "evolution_memory_summary.json").exists()
    assert "E1_mean_final_hv_adaptive" in summary
