"""Phase5-R3-R2 tests: native schema, budget concurrency, memory/reflection effects."""

import threading
import pytest

from src.agent.genome import AgentGenome
from src.evaluation.schema_guard import SchemaMismatch, fail_closed_cross_benchmark, validate_episode_schema
from src.runtime.behavioral_agent import BehavioralAgent
from src.runtime.budget import BudgetExceeded, BudgetManager


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="self_critique", tool_policy="balanced",
                reasoning_budget=32)
    base.update(kw)
    return AgentGenome(**base)


# --- native schema ---
def test_native_schema_rejects_capability_prior():
    rec = {"evaluation_kind": "real_environment", "success": False, "steps": 1,
           "trajectory": [], "capability": 0.9}
    with pytest.raises(SchemaMismatch):
        validate_episode_schema(rec, "real_environment")


def test_native_schema_accepts_env_episode():
    rec = {"evaluation_kind": "real_environment", "success": True, "steps": 5,
           "trajectory": [{"t": 0}], "score": 1.0, "won": True}
    validate_episode_schema(rec, "real_environment")


def test_cross_benchmark_schema_fail_closed():
    train = [{"task_id": "x", "goal": "g", "difficulty": 0.5}]
    test = [{"task_id": "y", "gamefile": "/g", "split": "valid_unseen"}]
    with pytest.raises(SchemaMismatch):
        fail_closed_cross_benchmark(train, test, expected_schema_keys=["gamefile", "split"])


# --- budget concurrency ---
def test_budget_never_exceeds_max_calls_under_concurrency():
    bm = BudgetManager(max_calls=50, max_cost_usd=100.0, max_episode_steps=10**6)
    errors = []
    started = []

    def worker():
        for _ in range(20):
            try:
                rid = bm.reserve_call(0.0)
                started.append(rid)
                bm.settle_call(success=True, actual_cost=0.0)
            except BudgetExceeded:
                pass
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    snap = bm.snapshot()
    assert not errors
    assert snap["completed_calls"] + snap["failed_calls"] <= 50
    assert snap["reserved_calls"] == 0


def test_budget_cost_gate():
    bm = BudgetManager(max_calls=100, max_cost_usd=1.0)
    bm.reserve_call(0.6)
    bm.settle_call(success=True, actual_cost=0.6)
    with pytest.raises(BudgetExceeded):
        bm.reserve_call(0.6)


def test_episode_step_budget():
    bm = BudgetManager(max_episode_steps=5)
    for _ in range(5):
        bm.charge_steps(1)
    with pytest.raises(BudgetExceeded):
        bm.charge_steps(1)


# --- memory / reflection actually affect behavior ---
def test_memory_read_influences_prompt_path():
    agent = BehavioralAgent(g(memory_strategy="episodic"))
    # write then read
    assert agent.memory.write("fact-1") is True
    ctx = agent.memory.as_context()
    assert "fact-1" in ctx
    # none strategy: no context
    agent2 = BehavioralAgent(g(memory_strategy="none"))
    agent2.memory.write("fact-1")
    assert agent2.memory.as_context() == ""
    assert agent2.memory.reads == 0


def test_reflection_performs_second_pass():
    agent = BehavioralAgent(g(reflection_strategy="self_critique", tool_policy="balanced"))
    # force initial failure path: required tool blocked first via no_tools? use balanced + search
    out = agent.run_task("search something", required_tool="search")
    # reflection strategy != none should record at least one event OR success after retry
    # BehavioralAgent always emits reflect event when first outcome fails;
    # with balanced+search tool_ok may be true → no reflect. Use no_tools to fail then reflect.
    agent2 = BehavioralAgent(g(reflection_strategy="iterative", tool_policy="no_tools"))
    out2 = agent2.run_task("need search", required_tool="search")
    assert out2["success"] is False
    assert out2["reflection_events"] >= 1
    assert any(t.get("action") == "reflect" for t in out2["trajectory"])


def test_tool_allowlist_blocks_and_allows():
    blocked = BehavioralAgent(g(tool_policy="no_tools"))
    assert blocked.invoke_tool("search", query="x") is None
    allowed = BehavioralAgent(g(tool_policy="aggressive"))
    res = allowed.invoke_tool("search", query="x")
    assert res is not None
    assert res.ok is True


# --- random baseline independence ---
def test_random_search_is_not_nsga3_selection():
    # Random search = sample genomes only; NSGA-III uses non-dominated sorting.
    from src.evolution.nsga3 import non_dominated_sort

    rows = [[0.1, 0.1, 0.1, 0.1, 0.1], [0.9, 0.9, 0.1, 0.9, 0.9]]
    # This test asserts the sorting API exists separately from random sampling
    # (random search module does not call it).
    import src.evolution.operators as ops
    import inspect

    src = inspect.getsource(ops.mutate_genome)
    assert "non_dominated_sort" not in src
    assert non_dominated_sort([[1.0] * 5, [0.0] * 5])  # min semantics
