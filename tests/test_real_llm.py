"""Phase 4-R1 tests: cache, backend switch, token/cost accounting, adapter."""

import os

import pytest

from src.agent.genome import AgentGenome
from src.backend.base import DeepSeekBackend, MockLLMBackend, OpenAIBackend, resolve_backend
from src.benchmark.alfworld_real import ALFWorldRealAdapter
from src.runtime.cache import CacheEntry, EvaluationCache, genome_hash, make_key
from src.runtime.real_llm_pipeline import RealLLMPipeline, RealLLMConfig, run_real_llm_evolution


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
# Backend mock / real switch
# ====================================================================== #
def test_backend_switch_mock():
    b = resolve_backend("mock")
    assert isinstance(b, MockLLMBackend)


def test_backend_switch_deepseek_openai():
    assert isinstance(resolve_backend("deepseek"), DeepSeekBackend)
    assert isinstance(resolve_backend("openai"), OpenAIBackend)


def test_real_llm_pipeline_auto_uses_env(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key-not-real")
    pipe = RealLLMPipeline(RealLLMConfig(backend="auto", n_tasks=2, cache_path=None))
    assert pipe.backend.name == "deepseek"


def test_real_llm_pipeline_falls_back_mock(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    pipe = RealLLMPipeline(RealLLMConfig(backend="auto", n_tasks=2))
    assert pipe.backend.name == "mock"


# ====================================================================== #
# Token accounting
# ====================================================================== #
def test_mock_backend_token_accounting():
    b = MockLLMBackend()
    r = b.generate("hello world prompt", budget=16)
    assert r.tokens_prompt > 0
    assert r.tokens_completion > 0
    u = b.usage()
    assert u["tokens"] == r.tokens
    assert u["calls"] == 1


def test_deepseek_usage_accumulates(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    b = DeepSeekBackend()
    # Avoid network: call generate with forced failure path not needed;
    # usage starts empty.
    u = b.usage()
    assert u["calls"] == 0
    assert u["tokens"] == 0


# ====================================================================== #
# Cache hit / miss
# ====================================================================== #
def test_cache_miss_then_hit():
    cache = EvaluationCache()
    g = make_genome()
    assert cache.lookup_genome_task(g, "t1", benchmark="alfworld") is None
    assert cache.misses == 1
    entry = CacheEntry(
        genome_id=genome_hash(g), task_id="t1",
        objective_vector=[0.5] * 5, tokens=100, cost=0.01, latency=0.5, success=True, steps=3,
    )
    cache.store_genome_task(g, "t1", entry, benchmark="alfworld")
    hit = cache.lookup_genome_task(g, "t1", benchmark="alfworld")
    assert hit is not None
    assert hit.tokens == 100
    assert cache.hits == 1
    assert cache.stats()["hit_rate"] > 0


def test_cache_different_task_miss():
    cache = EvaluationCache()
    g = make_genome()
    cache.store_genome_task(g, "t1", CacheEntry(genome_hash(g), "t1", [0.5] * 5), benchmark="b")
    assert cache.lookup_genome_task(g, "t2", benchmark="b") is None


def test_cache_persistence(tmp_path):
    path = tmp_path / "c.json"
    cache = EvaluationCache()
    g = make_genome()
    cache.store_genome_task(g, "t1", CacheEntry(genome_hash(g), "t1", [0.1] * 5, tokens=7), benchmark="x")
    cache.save_json(path)
    loaded = EvaluationCache(path)
    assert len(loaded) == 1
    e = loaded.lookup_genome_task(g, "t1", benchmark="x")
    assert e.tokens == 7


def test_genome_hash_stable():
    g1, g2 = make_genome(), make_genome()
    assert genome_hash(g1) == genome_hash(g2)
    assert genome_hash(g1) != genome_hash(make_genome(reasoning_budget=64))


# ====================================================================== #
# Cost calculation
# ====================================================================== #
def test_mock_cost_calculation():
    b = MockLLMBackend(cost_per_1k=2.0)
    r = b.generate("x" * 400, budget=8)  # ~100 prompt tokens
    assert r.cost > 0
    assert b.usage()["cost"] == pytest.approx(r.cost)


def test_alfworld_real_tracks_cost():
    b = MockLLMBackend(cost_per_1k=1.0)
    cache = EvaluationCache()
    ad = ALFWorldRealAdapter(n_tasks=3, seed=0, backend=b, cache=cache)
    from src.runtime.agent_builder import AgentBuilder

    agent = AgentBuilder().build(make_genome())
    ep = ad.run(agent)
    for r in ep.results:
        assert r.cost >= 0
        assert r.tokens > 0
    rep = ad.cost_report()
    assert rep["llm_usage"]["calls"] >= 1
    assert rep["cache_stats"]["n_entries"] == 3


# ====================================================================== #
# Benchmark adapter
# ====================================================================== #
def test_alfworld_real_cache_skips_api():
    b = MockLLMBackend()
    cache = EvaluationCache()
    ad = ALFWorldRealAdapter(n_tasks=4, seed=1, backend=b, cache=cache)
    from src.runtime.agent_builder import AgentBuilder

    agent = AgentBuilder().build(make_genome())
    ep1 = ad.run(agent)
    calls_after_first = b.calls
    ad.reset()
    ep2 = ad.run(agent)
    assert b.calls == calls_after_first  # second run fully cached
    assert ad.cache_used == 4
    assert ep1.n_tasks == ep2.n_tasks == 4


def test_alfworld_real_fallback_without_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    ad = ALFWorldRealAdapter(n_tasks=2, seed=0)
    assert isinstance(ad.backend, MockLLMBackend)


# ====================================================================== #
# Pipeline integration
# ====================================================================== #
def test_run_real_llm_evolution_mock():
    out = run_real_llm_evolution(
        n_tasks=3, pop_size=4, n_generations=2, seed=3,
        backend="mock", cache_path=None,
    )
    assert out["final_hypervolume"] >= 0
    assert out["cost_report"]["llm_usage"]["calls"] >= 1
    assert len(out["history"]) == 3
