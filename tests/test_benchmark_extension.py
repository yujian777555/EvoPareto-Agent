"""Phase 5-Benchmark Extension tests: WebShop, NSGA-II, consistency, serialization."""

import json
from pathlib import Path

import pytest

import experiments.run_benchmark_extension as benchmark_extension

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.backend.base import MockLLMBackend
from src.benchmark.base_adapter import BenchmarkAdapter
from src.benchmark.webshop_real import WebShopRealAdapter
from src.evolution.nsga2_baseline import NSGA2, binary_tournament, crowding_distance
from src.runtime.agent_builder import AgentBuilder
from src.runtime.real_llm_pipeline import RealLLMConfig, RealLLMPipeline


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


# ====================================================================== #
# WebShop adapter
# ====================================================================== #
def test_webshop_real_is_adapter():
    ad = WebShopRealAdapter(n_tasks=4, seed=0, backend=MockLLMBackend())
    assert isinstance(ad, BenchmarkAdapter)
    assert ad.n_tasks == 4
    ad.reset()
    assert ad.n_tasks == 4


def test_webshop_real_run_and_evaluate():
    ad = WebShopRealAdapter(n_tasks=5, seed=1, backend=MockLLMBackend())
    agent = AgentBuilder().build(make_genome())
    ep = ad.run(agent)
    assert ep.n_tasks == 5
    m = ad.evaluate(ep)
    assert "success_rate" in m and "mean_cost" in m


def test_webshop_episode_schema():
    ad = WebShopRealAdapter(n_tasks=3, seed=2, backend=MockLLMBackend())
    agent = AgentBuilder().build(make_genome())
    ep, recs = ad.run_recorded(agent)
    d = recs[0].to_dict()
    for k in ("task_id", "genome" if "genome" in d else "agent_genome", "success",
              "steps", "tokens", "latency", "cost", "trajectory"):
        assert k in d or k == "genome"
    assert d["cost"] >= 0
    assert d["tokens"] > 0


def test_webshop_cache_hit():
    cache_backend = MockLLMBackend()
    from src.runtime.cache import EvaluationCache

    cache = EvaluationCache()
    ad = WebShopRealAdapter(n_tasks=3, seed=3, backend=cache_backend, cache=cache)
    agent = AgentBuilder().build(make_genome())
    ad.run(agent)
    calls = cache_backend.calls
    ad.reset()
    ad.run(agent)
    assert cache_backend.calls == calls
    assert ad.cache_used == 3


def test_webshop_different_genomes_differ():
    ad = WebShopRealAdapter(n_tasks=6, seed=0, backend=MockLLMBackend())
    weak = AgentBuilder().build(make_genome(tool_policy="no_tools", reasoning_budget=8))
    strong = AgentBuilder().build(make_genome(tool_policy="tool_first", reasoning_budget=128))
    e1, e2 = ad.run(weak), ad.run(strong)
    assert e1.to_dict()["results"] != e2.to_dict()["results"]


# ====================================================================== #
# NSGA-II correctness
# ====================================================================== #
def test_crowding_distance_bounds():
    rows = [[0.1, 0.9], [0.5, 0.5], [0.9, 0.1]]
    cd = crowding_distance(rows, maximize_input=False)
    assert cd[0] == float("inf") and cd[2] == float("inf")
    assert cd[1] < float("inf")


def test_nsga2_select_keeps_front():
    def ind(fit, i):
        return Individual(genome=make_genome(reasoning_budget=8 + 8 * i), fitness_vector=fit, generation=0)

    elite = ind([1.0, 1.0, 0.0, 1.0, 1.0], 0)
    mid = ind([0.5, 0.5, 0.5, 0.5, 0.5], 1)
    bad = ind([0.1, 0.1, 0.9, 0.1, 0.1], 2)
    nsga2 = NSGA2(n_objectives=5, seed=0)
    sel = nsga2.select([elite, mid, bad], 2)
    assert len(sel) == 2
    ids = {id(s) for s in sel}
    assert id(elite) in ids and id(mid) in ids


def test_binary_tournament_prefers_better_rank():
    import random

    rng = random.Random(0)
    win = binary_tournament(rng, 0, 1, ranks=[0, 1], crowding=[0.1, 0.9])
    assert win == 0


def test_nsga2_tournament_select():
    rng_pop = []
    for i in range(8):
        rng_pop.append(Individual(
            genome=make_genome(reasoning_budget=8 + 8 * i),
            fitness_vector=[i / 8, 1 - i / 8, 0.5, 0.5, 0.5],
            generation=0,
        ))
    nsga2 = NSGA2(seed=1)
    chosen = nsga2.tournament_select(rng_pop, n_select=4)
    assert len(chosen) == 4


def test_nsga2_sort_fronts_api():
    pop = [
        Individual(genome=make_genome(), fitness_vector=[1, 1, 0, 1, 1], generation=0),
        Individual(genome=make_genome(reasoning_budget=16), fitness_vector=[0, 0, 1, 0, 0], generation=0),
    ]
    nsga2 = NSGA2(seed=0)
    fronts = nsga2.sort_fronts(pop)
    assert fronts[0] == [0]


# ====================================================================== #
# Benchmark consistency
# ====================================================================== #
def test_real_pipeline_supports_webshop():
    pipe = RealLLMPipeline(RealLLMConfig(benchmark="webshop", n_tasks=3, backend="mock"))
    assert pipe.adapter.name == "webshop_real"
    vec = pipe.evaluate_genome(make_genome())
    assert len(vec) == 5


def test_real_pipeline_supports_alfworld():
    pipe = RealLLMPipeline(RealLLMConfig(benchmark="alfworld", n_tasks=3, backend="mock"))
    assert pipe.adapter.name == "alfworld_real"
    vec = pipe.evaluate_genome(make_genome())
    assert len(vec) == 5


def test_benchmarks_share_objective_schema():
    from src.benchmark.alfworld_real import ALFWorldRealAdapter

    a = ALFWorldRealAdapter(n_tasks=3, seed=0, backend=MockLLMBackend())
    w = WebShopRealAdapter(n_tasks=3, seed=0, backend=MockLLMBackend())
    agent = AgentBuilder().build(make_genome())
    ra = a.run_recorded(agent)[1][0].to_dict()
    rw = w.run_recorded(agent)[1][0].to_dict()
    assert set(ra.keys()) == set(rw.keys())


# ====================================================================== #
# Result serialization
# ====================================================================== #
def test_benchmark_extension_results_exist():
    root = Path(__file__).resolve().parents[2] / "results" / "benchmark_extension"
    for name in ("alfworld_final.json", "webshop_final.json", "nsga2_comparison.json", "pareto_curves.json"):
        p = root / name
        if p.exists():
            d = json.loads(p.read_text(encoding="utf-8"))
            assert d is not None


def test_summary_table_serializable():
    root = Path(__file__).resolve().parents[2] / "results" / "benchmark_extension" / "summary.json"
    if root.exists():
        d = json.loads(root.read_text(encoding="utf-8"))
        assert "alfworld" in d and "webshop" in d
        json.dumps(d)


def test_budget_equal_across_methods():
    root = Path(__file__).resolve().parents[2] / "results" / "benchmark_extension" / "summary.json"
    if root.exists():
        d = json.loads(root.read_text(encoding="utf-8"))
        cfg = d["config"]
        assert cfg["pop"] * (cfg["gens"] + 1) == cfg["budget_evals"]
        assert len(cfg["seeds"]) == 3

# ====================================================================== #
# Random-search baseline correctness
# ====================================================================== #
def test_random_search_is_independent_and_budget_matched(monkeypatch):
    class FakeAdapter:
        max_workers = 1

    class FakePipeline:
        instances = []

        def __init__(self, config, cache=None):
            self.config = config
            self.adapter = FakeAdapter()
            self.genomes = []
            self.__class__.instances.append(self)

        def evaluate_genome(self, genome):
            self.genomes.append(genome.key())
            x = genome.reasoning_budget / 128.0
            return [x, 1.0 - x, x / 1000.0, 0.5, 0.5]

    monkeypatch.setattr(benchmark_extension, "RealLLMPipeline", FakePipeline)
    monkeypatch.setattr(
        benchmark_extension,
        "CONFIG",
        {"pop": 2, "gens": 2, "tasks": 1, "seeds": [11], "budget_evals": 6},
    )

    result = benchmark_extension.run_random_search(benchmark="alfworld", seed=11)

    assert "B0_random_search" not in benchmark_extension.METHODS
    assert result["method"] == "B0_random_search"
    assert result["evaluation_protocol"] == "uniform_random_genomes_pareto_archive"
    assert result["evaluations"] == 6
    assert len(FakePipeline.instances[0].genomes) == 6
    assert [row["n_evaluations"] for row in result["curve"]] == [2, 4, 6]
    assert result["curve"][-1]["generation"] == 2
    assert result["final_hv"] >= 0.0

