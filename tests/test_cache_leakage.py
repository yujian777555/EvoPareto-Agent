"""Phase5-Audit-1: cache leakage isolation tests."""

import pytest

from src.agent.genome import AgentGenome
from src.runtime.cache import CacheEntry, EvaluationCache, genome_hash, make_key


def g(**kw):
    base = dict(
        planner_strategy="cot", memory_strategy="episodic",
        reflection_strategy="self_critique", tool_policy="balanced",
        reasoning_budget=32,
    )
    base.update(kw)
    return AgentGenome(**base)


def test_make_key_includes_all_components():
    genome = g()
    k = make_key(
        genome, task_id="t1", benchmark="alfworld", seed=1,
        backend="deepseek", model="deepseek-chat", preference="accuracy_first",
    )
    assert isinstance(k, str) and len(k) == 24


def test_key_isolated_by_task():
    genome = g()
    a = make_key(genome, task_id="t1", benchmark="b", seed=0)
    b = make_key(genome, task_id="t2", benchmark="b", seed=0)
    assert a != b


def test_key_isolated_by_benchmark():
    genome = g()
    a = make_key(genome, task_id="t1", benchmark="alfworld", seed=0)
    b = make_key(genome, task_id="t1", benchmark="webshop", seed=0)
    assert a != b


def test_key_isolated_by_seed():
    genome = g()
    a = make_key(genome, task_id="t1", benchmark="b", seed=0)
    b = make_key(genome, task_id="t1", benchmark="b", seed=1)
    assert a != b


def test_key_isolated_by_backend_and_model():
    genome = g()
    a = make_key(genome, task_id="t1", backend="mock", model="mock-llm")
    b = make_key(genome, task_id="t1", backend="deepseek", model="deepseek-chat")
    c = make_key(genome, task_id="t1", backend="deepseek", model="other-model")
    assert a != b
    assert b != c


def test_key_isolated_by_preference():
    genome = g()
    a = make_key(genome, task_id="t1", preference="accuracy_first")
    b = make_key(genome, task_id="t1", preference="cost_first")
    assert a != b


def test_key_isolated_by_genome():
    a = make_key(g(reasoning_budget=32), task_id="t1")
    b = make_key(g(reasoning_budget=64), task_id="t1")
    assert a != b


def test_no_cross_experiment_cache_reuse():
    """Different experiments (backend/seed/pref) must not share entries."""
    cache = EvaluationCache()
    genome = g()
    entry = CacheEntry(genome_hash(genome), "t1", [0.5] * 5, tokens=10, cost=0.01)
    cache.store_genome_task(
        genome, "t1", entry,
        benchmark="alfworld", seed=0, backend="mock", model="mock-llm",
        preference="balanced",
    )
    # Same call hits.
    assert cache.lookup_genome_task(
        genome, "t1", benchmark="alfworld", seed=0,
        backend="mock", model="mock-llm", preference="balanced",
    ) is not None
    # Different backend misses.
    assert cache.lookup_genome_task(
        genome, "t1", benchmark="alfworld", seed=0,
        backend="deepseek", model="deepseek-chat", preference="balanced",
    ) is None
    # Different preference misses.
    assert cache.lookup_genome_task(
        genome, "t1", benchmark="alfworld", seed=0,
        backend="mock", model="mock-llm", preference="cost_first",
    ) is None
    # Different seed misses.
    assert cache.lookup_genome_task(
        genome, "t1", benchmark="alfworld", seed=9,
        backend="mock", model="mock-llm", preference="balanced",
    ) is None


def test_legacy_keys_still_distinct_without_new_fields():
    genome = g()
    k1 = make_key(genome, task_id="t1", benchmark="b", seed=0)
    k2 = make_key(genome, task_id="t1", benchmark="b", seed=0, backend="", model="", preference="")
    assert k1 == k2  # empty fields are stable defaults
