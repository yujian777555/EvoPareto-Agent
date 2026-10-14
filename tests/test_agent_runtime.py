"""Phase 1 tests: Agent runtime execution."""

from src.agent.genome import AgentGenome
from src.runtime.agent_builder import AgentBuilder
from src.runtime.agent_runner import AgentRunner, run_agent
from src.runtime.result import EpisodeResult, TaskResult
from src.runtime.task import TaskSpec, TaskSuite


def make_agent(**kwargs) -> object:
    g = AgentGenome(
        planner_strategy=kwargs.get("planner_strategy", "cot"),
        memory_strategy=kwargs.get("memory_strategy", "episodic"),
        reflection_strategy=kwargs.get("reflection_strategy", "self_critique"),
        tool_policy=kwargs.get("tool_policy", "balanced"),
        reasoning_budget=kwargs.get("reasoning_budget", 32),
    )
    return AgentBuilder().build(g)


def test_agent_run_task_returns_task_result():
    agent = make_agent()
    task = TaskSpec(task_id="t1", goal="demo", difficulty=0.4)
    result = agent.run_task(task, seed=0)
    assert isinstance(result, TaskResult)
    assert result.task_id == "t1"
    assert result.steps >= 1
    assert result.tokens >= 1
    assert result.latency >= 0
    assert result.cost >= 0
    assert isinstance(result.success, bool)


def test_agent_run_is_deterministic():
    agent = make_agent()
    task = TaskSpec(task_id="t1", goal="demo", difficulty=0.5)
    r1 = agent.run_task(task, seed=3)
    r2 = agent.run_task(task, seed=3)
    assert r1.to_dict() == r2.to_dict()


def test_different_genomes_different_results():
    weak = make_agent(
        planner_strategy="direct",
        memory_strategy="none",
        reflection_strategy="none",
        tool_policy="no_tools",
        reasoning_budget=8,
    )
    strong = make_agent(
        planner_strategy="tree_search",
        memory_strategy="hybrid",
        reflection_strategy="iterative",
        tool_policy="tool_first",
        reasoning_budget=128,
    )
    task = TaskSpec(
        task_id="hard",
        goal="needs tools",
        difficulty=0.85,
        required_tools=("search", "calculator"),
    )
    rw = weak.run_task(task, seed=0)
    rs = strong.run_task(task, seed=0)
    assert rw.to_dict() != rs.to_dict()
    # Strong config should succeed more often on a hard tool task.
    assert rs.success is True or rw.success is False


def test_runner_suite_aggregates():
    agent = make_agent()
    suite = TaskSuite(
        name="s",
        tasks=(
            TaskSpec(task_id="a", goal="a", difficulty=0.3),
            TaskSpec(task_id="b", goal="b", difficulty=0.6),
            TaskSpec(task_id="c", goal="c", difficulty=0.9),
        ),
    )
    episode = AgentRunner(default_seed=1).run_suite(agent, suite)
    assert isinstance(episode, EpisodeResult)
    assert episode.n_tasks == 3
    assert 0.0 <= episode.success_rate <= 1.0
    totals = episode.totals()
    assert totals["mean_steps"] > 0
    assert totals["mean_tokens"] > 0


def test_run_agent_helper():
    agent = make_agent()
    task = TaskSpec(task_id="t", goal="g", difficulty=0.2)
    assert isinstance(run_agent(agent, task), TaskResult)


def test_task_result_validation():
    import pytest

    with pytest.raises(ValueError):
        TaskResult(task_id="x", success=True, steps=-1, tokens=1, latency=1.0, cost=0.0)
