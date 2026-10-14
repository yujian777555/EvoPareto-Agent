"""Phase 4 tests: backend abstraction, adapters, objectives, cost, pipeline."""

import os

import pytest

from src.agent.genome import AgentGenome
from src.backend.base import (
    DeepSeekBackend,
    LLMResponse,
    MockLLMBackend,
    OpenAIBackend,
    get_env_key,
    resolve_backend,
)
from src.benchmark.alfworld import ALFWorldAdapter, RealALFWorldAdapter
from src.benchmark.base_adapter import BenchmarkAdapter, episode_metrics
from src.benchmark.webshop import WebShopAdapter, RealWebShopAdapter
from src.evaluation.objective_evaluator import ObjectiveEvaluator
from src.evaluation.objectives import OBJECTIVE_NAMES, to_minimization
from src.runtime.agent_builder import AgentBuilder
from src.runtime.real_pipeline import RealBenchmarkPipeline, RealEvalConfig, run_real_agent_evolution


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
# 1. Backend abstraction
# ====================================================================== #
def test_mock_backend_deterministic():
    b = MockLLMBackend()
    r1 = b.generate("hello", budget=16)
    r2 = b.generate("hello", budget=16)
    assert r1.text == r2.text
    assert isinstance(r1, LLMResponse)
    assert r1.tokens > 0


def test_mock_backend_no_network_needed():
    b = resolve_backend("mock")
    assert b.name == "mock"
    assert b.generate("x").text


def test_openai_backend_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    b = OpenAIBackend()
    assert not b.has_credentials()
    with pytest.raises(RuntimeError):
        b.generate("hi")


def test_deepseek_backend_requires_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    b = DeepSeekBackend()
    assert not b.has_credentials()
    with pytest.raises(RuntimeError):
        b.generate("hi")


def test_api_keys_not_in_source():
    # Keys must come from env, never hard-coded.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    backend_src = open(os.path.join(root, "src", "backend", "base.py"), encoding="utf-8").read()
    assert "sk-" not in backend_src
    assert "OPENAI_API_KEY" in backend_src
    assert "DEEPSEEK_API_KEY" in backend_src


def test_get_env_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "abc")
    assert get_env_key("OPENAI_API_KEY") == "abc"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert get_env_key("OPENAI_API_KEY") is None


def test_resolve_backend_factory():
    assert resolve_backend("mock").name == "mock"
    assert resolve_backend("openai").name == "openai"
    assert resolve_backend("deepseek").name == "deepseek"
    with pytest.raises(ValueError):
        resolve_backend("nope")


# ====================================================================== #
# 2. Environment adapter
# ====================================================================== #
def test_alfworld_adapter_interface():
    a = ALFWorldAdapter(n_tasks=6, seed=0)
    assert isinstance(a, BenchmarkAdapter)
    assert a.n_tasks == 6
    a.reset()
    agent = AgentBuilder().build(make_genome())
    ep = a.run(agent)
    assert ep.n_tasks == 6
    metrics = a.evaluate(ep)
    assert "success_rate" in metrics


def test_webshop_adapter_interface():
    a = WebShopAdapter(n_tasks=5, seed=1)
    agent = AgentBuilder().build(make_genome())
    ep = a.run(agent)
    assert ep.n_tasks == 5
    assert 0.0 <= ep.success_rate <= 1.0


def test_adapters_different_genomes_differ():
    a = ALFWorldAdapter(n_tasks=8, seed=0)
    weak = AgentBuilder().build(make_genome(planner_strategy="direct", tool_policy="no_tools", reasoning_budget=8))
    strong = AgentBuilder().build(make_genome(planner_strategy="tree_search", tool_policy="tool_first", reasoning_budget=128))
    e1, e2 = a.run(weak), a.run(strong)
    assert e1.to_dict()["results"] != e2.to_dict()["results"]


def test_real_adapter_flags():
    ra = RealALFWorldAdapter(n_tasks=2)
    rw = RealWebShopAdapter(n_tasks=2)
    assert hasattr(ra, "available")
    assert hasattr(rw, "available")


# ====================================================================== #
# 3. Objective conversion
# ====================================================================== #
def test_objectives_from_real_episode():
    a = ALFWorldAdapter(n_tasks=6, seed=2)
    agent = AgentBuilder().build(make_genome())
    ep = a.run(agent)
    vec = ObjectiveEvaluator().from_episode(ep)
    assert len(vec) == 5
    assert all(0.0 <= v <= 1.0 for v in vec)
    assert list(OBJECTIVE_NAMES) == ["performance", "efficiency", "cost", "robustness", "autonomy"]
    assert to_minimization(vec)[2] == vec[2]  # cost sign


def test_episode_metrics_keys():
    a = WebShopAdapter(n_tasks=4, seed=3)
    m = a.evaluate(a.run(AgentBuilder().build(make_genome())))
    for k in ("success_rate", "mean_steps", "mean_tokens", "mean_latency", "mean_cost"):
        assert k in m


# ====================================================================== #
# 4. Cost tracking + trajectory records
# ====================================================================== #
def test_episode_records_schema():
    a = ALFWorldAdapter(n_tasks=3, seed=4)
    agent = AgentBuilder().build(make_genome())
    ep, recs = a.run_recorded(agent)
    assert len(recs) == 3
    d = recs[0].to_dict()
    for k in ("task_id", "agent_genome", "success", "steps", "tokens", "latency", "cost", "trajectory"):
        assert k in d
    assert isinstance(d["agent_genome"], dict)
    assert d["cost"] >= 0
    assert d["tokens"] > 0


def test_cost_tracking_nonnegative_and_backend_used():
    backend = MockLLMBackend(cost_per_1k=1.0)
    a = WebShopAdapter(n_tasks=4, seed=5, backend=backend)
    agent = AgentBuilder().build(make_genome(reasoning_budget=128, tool_policy="tool_first"))
    ep = a.run(agent)
    for r in ep.results:
        assert r.cost >= 0
        assert r.tokens > 0
        assert r.metadata["backend"] == "mock"


# ====================================================================== #
# 5. Real pipeline integration
# ====================================================================== #
def test_real_pipeline_evaluate_genome():
    pipe = RealBenchmarkPipeline(RealEvalConfig(benchmark="alfworld", n_tasks=5, seed=0))
    vec = pipe.evaluate_genome(make_genome())
    assert len(vec) == 5


def test_run_real_agent_evolution_end_to_end():
    out = run_real_agent_evolution(
        benchmark="webshop",
        n_tasks=5,
        pop_size=10,
        n_generations=3,
        seed=7,
        preference="cost_first",
    )
    assert out["final_pareto_size"] >= 1
    assert out["benchmark"]["benchmark"] == "webshop"
    assert out["preference"] is not None
    assert len(out["history"]) == 4
    assert out["episodes"]  # recorded trajectories


def test_run_real_agent_evolution_alfworld_no_pref():
    out = run_real_agent_evolution(
        benchmark="alfworld",
        n_tasks=4,
        pop_size=8,
        n_generations=2,
        seed=8,
        preference=None,
    )
    assert out["final_hypervolume"] >= 0
    assert out["preference"] is None
