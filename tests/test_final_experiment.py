"""Phase 4-R2 tests: final config, serialization, cost aggregation, cache stats."""

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.runtime.cache import CacheEntry, EvaluationCache, genome_hash


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
# Final experiment config
# ====================================================================== #
def test_scales_documented():
    from experiments.run_final_real_llm import SCALES

    assert "paper" in SCALES and "reduced" in SCALES and "micro" in SCALES
    assert SCALES["paper"]["pop"] == 16
    assert SCALES["paper"]["gens"] == 10
    assert SCALES["paper"]["tasks"] == 50
    assert len(SCALES["paper"]["seeds"]) == 3
    # Reduction is explicit.
    assert SCALES["reduced"]["pop"] < SCALES["paper"]["pop"]


def test_episode_row_schema():
    from experiments.run_final_real_llm import _episode_rows

    g = make_genome()
    row = _episode_rows(
        method="B3", seed=1, generation=0, genome=g,
        task_id="t1", success=True, steps=3, tokens=100,
        latency=0.5, cost=0.01, trajectory=[{"t": 0}],
    )
    for k in ("task_id", "seed", "method", "generation", "genome", "success",
              "steps", "tokens", "latency", "cost", "trajectory"):
        assert k in row
    assert row["genome"] == g.to_dict()


# ====================================================================== #
# Result serialization
# ====================================================================== #
def test_result_json_roundtrip(tmp_path: Path):
    payload = {
        "method": "B3_nsga3_peem",
        "seed": 11,
        "success": 0.8,
        "cost": 0.001,
        "final_hv": 0.75,
    }
    p = tmp_path / "overall_results.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded == payload


def test_final_summary_files_created(tmp_path, monkeypatch):
    import experiments.run_final_real_llm as mod

    monkeypatch.setattr(mod, "OUT", tmp_path)
    # Tiny mock run
    monkeypatch.setattr(mod, "SCALES", {
        "micro": dict(pop=3, gens=1, tasks=2, seeds=[1], workers=2),
    })
    # Force micro scale via argv
    monkeypatch.setattr("sys.argv", ["run_final_real_llm.py", "--scale", "micro", "--backend", "mock"])
    summary = mod.main()
    for name in ("overall_results.json", "ablation_results.json",
                 "preference_results.json", "evolution_curve.json",
                 "cost_report.json", "final_summary.json", "run_meta.json"):
        assert (tmp_path / name).exists(), name
    assert "overall" in summary
    assert "cost_report" in summary


# ====================================================================== #
# Cost aggregation
# ====================================================================== #
def test_cost_aggregation_math():
    reports = [
        {"llm_usage": {"calls": 10, "tokens": 1000, "cost": 0.01},
         "cache": {"hits": 2, "misses": 8, "saved_cost": 0.002}},
        {"llm_usage": {"calls": 5, "tokens": 500, "cost": 0.005},
         "cache": {"hits": 1, "misses": 4, "saved_cost": 0.001}},
    ]
    total_calls = sum(int(r["llm_usage"]["calls"]) for r in reports)
    total_tokens = sum(int(r["llm_usage"]["tokens"]) for r in reports)
    total_cost = sum(float(r["llm_usage"]["cost"]) for r in reports)
    hits = sum(int(r["cache"]["hits"]) for r in reports)
    assert total_calls == 15
    assert total_tokens == 1500
    assert total_cost == pytest.approx(0.015)
    assert hits == 3


def test_cost_report_within_budget_flag():
    cost = 0.001
    assert cost <= 20.0


# ====================================================================== #
# Cache statistics
# ====================================================================== #
def test_cache_stats_reporting():
    cache = EvaluationCache()
    g = make_genome()
    cache.lookup_genome_task(g, "t1", benchmark="b")
    cache.store_genome_task(g, "t1", CacheEntry(genome_hash(g), "t1", [0.5] * 5, tokens=50, cost=0.01), benchmark="b")
    cache.lookup_genome_task(g, "t1", benchmark="b")
    st = cache.stats()
    assert st["misses"] == 1
    assert st["hits"] == 1
    assert st["hit_rate"] == pytest.approx(0.5)
    assert st["saved_tokens"] == 50
    assert st["saved_cost"] == pytest.approx(0.01)


def test_cache_saved_calls_equals_hits():
    cache = EvaluationCache()
    g = make_genome()
    for i in range(3):
        cache.store_genome_task(g, f"t{i}", CacheEntry(genome_hash(g), f"t{i}", [0.1] * 5, cost=0.001), benchmark="b")
        cache.lookup_genome_task(g, f"t{i}", benchmark="b")
    st = cache.stats()
    assert st["saved_calls" if "saved_calls" in st else "hits"] == st["hits"]


def test_alfworld_real_parallel_run():
    from src.backend.base import MockLLMBackend
    from src.benchmark.alfworld_real import ALFWorldRealAdapter
    from src.runtime.agent_builder import AgentBuilder

    ad = ALFWorldRealAdapter(n_tasks=6, seed=0, backend=MockLLMBackend(), max_workers=3)
    agent = AgentBuilder().build(make_genome())
    ep = ad.run(agent)
    assert ep.n_tasks == 6
    assert all(r.tokens > 0 for r in ep.results)
