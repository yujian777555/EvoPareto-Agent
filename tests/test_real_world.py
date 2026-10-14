"""Phase 5-R1 tests: tools, real-world adapter, serialization, aggregation."""

import json
from pathlib import Path

import pytest

from src.agent.genome import AgentGenome
from src.benchmark.real_world_agent import RealWorldAgentBenchmark, _build_catalog
from src.runtime.agent_builder import AgentBuilder
from src.tools.calculator import calculate
from src.tools.file_tool import file_list, file_read
from src.tools.registry import ToolRegistry, default_registry
from src.tools.search_tool import search


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
# Tool execution
# ====================================================================== #
def test_calculator_ok():
    r = calculate("17+25*3")
    assert r.ok and r.output == pytest.approx(92.0)


def test_calculator_rejects_unsafe():
    r = calculate("__import__('os')")
    assert not r.ok


def test_search_tool():
    r = search("climate change facts")
    assert r.ok and len(r.output) >= 1


def test_file_tools():
    assert file_read("notes.txt").ok
    assert file_list().ok
    assert not file_read("missing.txt").ok


def test_tool_registry_logs_calls():
    reg = default_registry()
    reg.invoke("calculator", expression="1+1")
    reg.invoke("search", query="python")
    assert len(reg.calls) == 2
    log = reg.call_log()
    assert log[0]["name"] == "calculator"
    assert log[0]["ok"] is True
    assert log[1]["name"] == "search"


# ====================================================================== #
# Benchmark adapter
# ====================================================================== #
def test_catalog_has_50_tasks():
    cat = _build_catalog()
    assert len(cat) == 50
    cats = {t["category"] for t in cat}
    assert cats == {"information", "reasoning", "tool"}


def test_real_world_adapter_interface():
    b = RealWorldAgentBenchmark(n_tasks=10, seed=0)
    b.reset()
    assert b.n_tasks == 10
    agent = AgentBuilder().build(make_genome())
    ep = b.run(agent)
    assert ep.n_tasks == 10
    m = b.evaluate(ep)
    assert "success_rate" in m and "tool_success" in m


def test_episode_has_tool_calls():
    b = RealWorldAgentBenchmark(n_tasks=5, seed=1)
    agent = AgentBuilder().build(make_genome())
    ep, recs = b.run_recorded(agent)
    d = recs[0].to_dict()
    for k in ("task_id", "success", "steps", "tokens", "latency", "cost", "trajectory"):
        assert k in d
    assert "tool_calls" in d or "tool_calls" in (recs[0].metadata or {})
    # metadata carries tool_calls
    assert recs[0].metadata.get("tool_calls") is not None


def test_train_test_split():
    train = RealWorldAgentBenchmark(n_tasks=50, split="train")
    test = RealWorldAgentBenchmark(n_tasks=50, split="test")
    tr_ids = {t["task_id"] for t in train._tasks}
    te_ids = {t["task_id"] for t in test._tasks}
    assert tr_ids and te_ids
    assert not (tr_ids & te_ids)
    assert len(tr_ids) + len(te_ids) == 50


# ====================================================================== #
# Task serialization / result aggregation
# ====================================================================== #
def test_catalog_serializable():
    cat = _build_catalog()
    json.dumps(cat)
    assert all("difficulty" in t and 0 < t["difficulty"] <= 1 for t in cat)


def test_cache_roundtrip_real_world(tmp_path):
    from src.runtime.cache import EvaluationCache

    cache = EvaluationCache(tmp_path / "c.json")
    b = RealWorldAgentBenchmark(n_tasks=3, seed=0, cache=cache)
    agent = AgentBuilder().build(make_genome())
    b.run(agent)
    b.reset()
    b.run(agent)
    assert b.cache_used == 3
    cache.save_json(tmp_path / "c.json")
    loaded = EvaluationCache(tmp_path / "c.json")
    assert len(loaded) == 3


def test_different_genomes_different_behavior():
    b = RealWorldAgentBenchmark(n_tasks=8, seed=0)
    weak = AgentBuilder().build(make_genome(tool_policy="no_tools", reasoning_budget=8))
    strong = AgentBuilder().build(make_genome(tool_policy="tool_first", reasoning_budget=128))
    e1, e2 = b.run(weak), b.run(strong)
    assert e1.to_dict()["results"] != e2.to_dict()["results"]


def test_real_world_results_exist():
    root = Path(__file__).resolve().parents[2] / "results" / "real_world"
    for name in ("overall.json", "preference.json", "transfer.json", "trajectory.json"):
        p = root / name
        if p.exists():
            assert json.loads(p.read_text(encoding="utf-8")) is not None


def test_summary_aggregation():
    root = Path(__file__).resolve().parents[2] / "results" / "real_world" / "summary.json"
    if root.exists():
        d = json.loads(root.read_text(encoding="utf-8"))
        assert "overall" in d and "transfer" in d
        assert d["config"]["tasks"] == 50
        assert len(d["config"]["seeds"]) == 3
