"""Phase 1 tests: benchmark adapter + objective vector + E2E pipeline."""

import json

from src.agent.genome import AgentGenome
from src.benchmark.base import Benchmark
from src.benchmark.mock_benchmark import MockBenchmark, default_mock_suite
from src.evaluation.objective_evaluator import ObjectiveEvaluator
from src.evaluation.objectives import OBJECTIVE_NAMES, to_minimization
from src.runtime.agent_builder import AgentBuilder
from src.runtime.result import EpisodeResult, TaskResult
from src.runtime.task import TaskSpec
from src.runtime.pipeline import AgentEvaluationPipeline, build_default_pipeline, run_agent_evolution


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


# ------------------------------------------------------------------ #
# 3. Benchmark adapter
# ------------------------------------------------------------------ #
def test_mock_benchmark_is_benchmark_subclass():
    b = MockBenchmark(n_tasks=5, seed=0)
    assert isinstance(b, Benchmark)
    assert b.n_tasks == 5


def test_mock_benchmark_evaluate_agent():
    b = MockBenchmark(n_tasks=6, seed=0)
    agent = AgentBuilder().build(make_genome())
    episode = b.evaluate(agent)
    assert isinstance(episode, EpisodeResult)
    assert episode.n_tasks == 6
    assert all(isinstance(r, TaskResult) for r in episode.results)


def test_mock_benchmark_genomes_differ():
    b = MockBenchmark(n_tasks=8, seed=1)
    a1 = AgentBuilder().build(make_genome(planner_strategy="direct", tool_policy="no_tools", reasoning_budget=8))
    a2 = AgentBuilder().build(make_genome(planner_strategy="tree_search", tool_policy="tool_first", reasoning_budget=128))
    e1 = b.evaluate(a1)
    e2 = b.evaluate(a2)
    assert e1.to_dict()["results"] != e2.to_dict()["results"]


def test_default_mock_suite_valid():
    suite = default_mock_suite(4)
    assert len(suite) == 4
    assert all(0 < t.difficulty <= 1 for t in suite)


# ------------------------------------------------------------------ #
# 4. Objective vector correctness
# ------------------------------------------------------------------ #
def test_objective_vector_shape_and_range():
    ev = ObjectiveEvaluator()
    b = MockBenchmark(n_tasks=6, seed=0)
    agent = AgentBuilder().build(make_genome())
    vec = ev.from_episode(b.evaluate(agent))
    assert len(vec) == 5
    assert all(0.0 <= v <= 1.0 for v in vec)


def test_objective_names_and_directions():
    ev = ObjectiveEvaluator()
    assert list(ev.names()) == list(OBJECTIVE_NAMES)
    assert OBJECTIVE_NAMES[2] == "cost"
    raw = [0.7, 0.6, 0.2, 0.8, 0.9]
    assert ev.to_minimization(raw) == to_minimization(raw)


def test_objective_evaluator_prefers_success():
    ev = ObjectiveEvaluator()
    ok = [
        TaskResult("t", True, steps=10, tokens=100, latency=10.0, cost=0.05,
                   metadata={"difficulty": 0.5, "reflection": "none", "tool_policy": "balanced", "reasoning_budget": 32}),
    ]
    bad = [
        TaskResult("t", False, steps=40, tokens=900, latency=50.0, cost=0.5,
                   metadata={"difficulty": 0.5, "reflection": "critic_model", "tool_policy": "tool_first", "reasoning_budget": 128}),
    ]
    v_ok = ev.from_results(ok)
    v_bad = ev.from_results(bad)
    assert v_ok[0] > v_bad[0]  # performance
    assert v_ok[1] > v_bad[1]  # efficiency
    assert v_ok[2] < v_bad[2]  # cost (lower better)
    assert v_ok[4] > v_bad[4]  # autonomy


def test_objective_vector_deterministic():
    ev = ObjectiveEvaluator()
    b = MockBenchmark(n_tasks=5, seed=2)
    agent = AgentBuilder().build(make_genome())
    assert ev.from_episode(b.evaluate(agent)) == ev.from_episode(b.evaluate(agent))


# ------------------------------------------------------------------ #
# 5. End-to-end evolution pipeline
# ------------------------------------------------------------------ #
def test_pipeline_evaluate_genome():
    pipe = build_default_pipeline(n_tasks=6, seed=0)
    vec = pipe.evaluate_genome(make_genome())
    assert len(vec) == 5


def test_run_agent_evolution_produces_front_and_history():
    out = run_agent_evolution(pop_size=12, n_generations=3, n_tasks=6, seed=5)
    pop = out["population"]
    front = out["front"]
    assert len(pop.individuals) == 12
    assert pop.generation == 3
    assert len(out["history"]) == 4  # init + 3 gens
    assert len(front) >= 1
    for ind in front:
        assert ind.has_fitness()
        assert len(ind.fitness_vector) == 5


def test_evolution_improves_or_spreads_on_front():
    """NSGA-III should keep non-dominated agents with mixed-direction ranks."""
    from src.utils.pareto import pareto_mask_mixed

    out = run_agent_evolution(pop_size=16, n_generations=4, n_tasks=8, seed=11)
    pop = out["population"]
    rows = [list(ind.fitness_vector) for ind in pop.individuals]
    mask = pareto_mask_mixed(rows)
    assert sum(mask) >= 1
    # Front from NSGA-III must be subset of mixed non-dominated set.
    front_rows = {tuple(ind.fitness_vector) for ind in out["front"]}
    nd_rows = {tuple(rows[i]) for i, m in enumerate(mask) if m}
    assert front_rows <= nd_rows


def test_phase1_demo_writes_results(tmp_path, monkeypatch):
    # Run demo logic into a temp results dir via monkeypatch of RESULTS_DIR.
    import experiments.run_agent_evolution_demo as demo

    monkeypatch.setattr(demo, "RESULTS_DIR", tmp_path)
    summary = demo.main()
    assert (tmp_path / "agent_population_history.json").exists()
    assert (tmp_path / "agent_pareto_front.json").exists()
    assert (tmp_path / "agent_evolution_summary.json").exists()
    data = json.loads((tmp_path / "agent_pareto_front.json").read_text(encoding="utf-8"))
    assert data["n_points"] == summary["pareto_size"]
