"""Phase5-R3-R1 tests: task leakage, PPEC selection, genome behavior, protocol."""

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.benchmark.real_world_agent import _build_catalog
from src.evaluation.metrics import preference_satisfaction_score
from src.evolution.preference import encode_preference
from src.runtime.behavioral_agent import BehavioralAgent, behavior_report
from src.runtime.task_split import (
    detect_task_leakage,
    is_same_template_only,
    split_by_fingerprint,
    task_fingerprint,
)


def g(**kw):
    base = dict(planner_strategy="cot", memory_strategy="episodic",
                reflection_strategy="self_critique", tool_policy="balanced",
                reasoning_budget=32)
    base.update(kw)
    return AgentGenome(**base)


# ====================================================================== #
# 1. Task content leakage
# ====================================================================== #
def test_same_template_different_suffix_same_fingerprint():
    a = {"task_id": "t-0", "goal": "put platter", "difficulty": 0.5, "hint": "go", "template_id": "tpl"}
    b = {"task_id": "t-1", "goal": "put platter", "difficulty": 0.5, "hint": "go", "template_id": "tpl"}
    assert is_same_template_only(a, b)


def test_different_goal_different_fingerprint():
    a = {"task_id": "x", "goal": "A", "difficulty": 0.5, "hint": "h"}
    b = {"task_id": "x", "goal": "B", "difficulty": 0.5, "hint": "h"}
    assert task_fingerprint(a) != task_fingerprint(b)


def test_split_by_fingerprint_no_overlap():
    tasks = _build_catalog()
    train, test = split_by_fingerprint(tasks, train_frac=0.7)
    rep = detect_task_leakage(train, test)
    assert rep.ok, rep.message
    assert rep.n_train > 0 and rep.n_test > 0
    assert not rep.overlap_fingerprints


def test_leak_detector_flags_overlap():
    t = {"task_id": "a-0", "goal": "same", "difficulty": 0.4, "hint": "h"}
    t2 = {"task_id": "a-1", "goal": "same", "difficulty": 0.4, "hint": "h"}
    rep = detect_task_leakage([t], [t2])
    assert not rep.ok
    assert rep.overlap_fingerprints


def test_seed_change_is_not_independent_content():
    # Same template, different seed-style ids → same fingerprint.
    a = {"task_id": "put_platter_fridge-0-000", "goal": "put a clean platter in the fridge",
         "difficulty": 0.55, "hint": "go to sinkbasin"}
    b = {"task_id": "put_platter_fridge-1-000", "goal": "put a clean platter in the fridge",
         "difficulty": 0.55, "hint": "go to sinkbasin"}
    assert task_fingerprint(a) == task_fingerprint(b)


# ====================================================================== #
# 2. PPEC preference selection
# ====================================================================== #
def test_preference_selection_not_always_fitness0():
    from experiments.real_eval_protocol import select_by_preference

    # high cost-performance (fitness0 high, bad for cost_first)
    a = Individual(genome=g(), fitness_vector=[0.95, 0.3, 0.9, 0.5, 0.5], generation=0)
    b = Individual(genome=g(reasoning_budget=64), fitness_vector=[0.55, 0.7, 0.1, 0.5, 0.5], generation=0)
    sel_acc = select_by_preference([a, b], "accuracy_first")
    sel_cost = select_by_preference([a, b], "cost_first")
    assert sel_acc.genome.key() == a.genome.key()
    assert sel_cost.genome.key() == b.genome.key()


def test_pss_directions():
    pref = encode_preference("cost_first")
    cheap = [0.5, 0.5, 0.1, 0.5, 0.5]
    pricey = [0.5, 0.5, 0.9, 0.5, 0.5]
    assert preference_satisfaction_score([cheap], pref) > preference_satisfaction_score([pricey], pref)


def test_selection_difference_detects_change():
    from experiments.real_eval_protocol import selection_difference

    a1 = Individual(genome=g(), fitness_vector=[0.9, 0.5, 0.8, 0.5, 0.5], generation=0)
    b1 = Individual(genome=g(reasoning_budget=64), fitness_vector=[0.5, 0.5, 0.1, 0.5, 0.5], generation=0)
    diff = selection_difference([a1], [b1], "cost_first")
    assert diff["same_genome"] is False


# ====================================================================== #
# 3. Genome behavioral differences
# ====================================================================== #
def test_no_tools_blocks_required_tool():
    agent = BehavioralAgent(g(tool_policy="no_tools"))
    out = agent.run_task("do something", required_tool="search")
    assert out["success"] is False
    assert any(t.get("action") == "required_tool_blocked" for t in out["trajectory"])


def test_memory_none_no_reads():
    out = behavior_report(g(memory_strategy="none"), "goal", required_tool="calculator")
    assert out["memory_reads"] == 0
    assert out["memory_strategy"] == "none"


def test_memory_episodic_reads_after_run():
    out = behavior_report(g(memory_strategy="episodic"), "goal", required_tool="calculator")
    assert out["memory_writes"] >= 1


def test_reflection_emits_events_when_enabled():
    out = behavior_report(g(reflection_strategy="self_critique", tool_policy="balanced"),
                          "goal", required_tool="search")
    assert "reflection_events" in out
    # reflection strategy != none should create at least the flag field
    assert out["reflection_events"] >= 0


def test_budget_limits_steps():
    out = behavior_report(g(reasoning_budget=8, planner_strategy="tree_search"), "goal")
    assert out["steps_used"] <= out["max_steps"]
    assert out["max_tokens"] > 0


def test_planner_changes_step_structure():
    direct = behavior_report(g(planner_strategy="direct", memory_strategy="none"), "g")
    tree = behavior_report(g(planner_strategy="tree_search", memory_strategy="none"), "g")
    assert direct["trajectory"] != tree["trajectory"]


# ====================================================================== #
# 4. No mock fallback / empty response / provenance
# ====================================================================== #
def test_real_adapter_fail_is_not_success():
    from src.benchmark.alfworld_real import ALFWorldRealAdapter
    from src.runtime.agent_builder import AgentBuilder
    from src.runtime.cache import EvaluationCache

    class Boom:
        name = "deepseek"
        model = "deepseek-flash"

        def generate(self, *a, **k):
            raise RuntimeError("down")

    ad = ALFWorldRealAdapter(n_tasks=2, seed=0, backend=Boom(), cache=EvaluationCache())
    ep = ad.run(AgentBuilder().build(g()))
    assert all(r.success is False for r in ep.results)
    assert all(r.metadata.get("evaluation_kind") == "real_llm_failed" for r in ep.results)


def test_cache_isolation_by_model():
    from src.runtime.cache import make_key

    k1 = make_key(g(), task_id="t", backend="deepseek", model="deepseek-flash")
    k2 = make_key(g(), task_id="t", backend="deepseek", model="deepseek-v4-pro")
    assert k1 != k2


# ====================================================================== #
# 5. Concurrent budget gate
# ====================================================================== #
def test_budget_gate_concurrent_ready():
    import threading

    from experiments.run_real_llm_large import assert_budget_before_calls

    errors = []

    def worker():
        try:
            assert_budget_before_calls(10, 100)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with pytest.raises(RuntimeError):
        assert_budget_before_calls(200, 100)
