"""Phase 1 tests: Genome -> Agent creation."""

from src.agent.genome import AgentGenome
from src.runtime.agent_builder import Agent, AgentBuilder, AgentConfig


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


def test_builder_creates_agent_with_genome_fields():
    g = make_genome()
    agent = AgentBuilder().build(g, agent_id=7)
    assert isinstance(agent, Agent)
    assert agent.agent_id == 7
    assert agent.planner_strategy == "cot"
    assert agent.memory_strategy == "episodic"
    assert agent.reflection_strategy == "self_critique"
    assert agent.tool_policy == "balanced"
    assert agent.reasoning_budget == 32


def test_builder_copies_genome():
    g = make_genome()
    agent = AgentBuilder().build(g)
    assert agent.genome == g
    assert agent.genome is not g


def test_agent_config_from_genome():
    g = make_genome(tree_search=True) if False else make_genome(planner_strategy="tree_search")
    cfg = AgentConfig.from_genome(g)
    assert cfg.planner_strategy == "tree_search"
    assert cfg.reasoning_budget == g.reasoning_budget


def test_builder_build_many():
    genomes = [make_genome(reasoning_budget=8), make_genome(reasoning_budget=64)]
    agents = AgentBuilder().build_many(genomes)
    assert [a.agent_id for a in agents] == [0, 1]
    assert agents[0].reasoning_budget == 8
    assert agents[1].reasoning_budget == 64


def test_builder_rejects_non_genome():
    import pytest

    with pytest.raises(TypeError):
        AgentBuilder().build({"planner_strategy": "cot"})  # type: ignore[arg-type]
