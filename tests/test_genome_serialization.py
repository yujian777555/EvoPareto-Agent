"""Genome serialization and comparison tests."""

import json

import pytest

from src.agent.genome import (
    MAX_BUDGET,
    MIN_BUDGET,
    AgentGenome,
)


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


def test_genome_construction_valid():
    g = make_genome()
    assert g.planner_strategy == "cot"
    assert g.reasoning_budget == 32


def test_genome_rejects_unknown_strategy():
    with pytest.raises(ValueError):
        make_genome(planner_strategy="nope")


def test_genome_rejects_bad_budget():
    with pytest.raises(ValueError):
        make_genome(reasoning_budget=MIN_BUDGET - 8)
    with pytest.raises(ValueError):
        make_genome(reasoning_budget=MAX_BUDGET + 8)


def test_to_dict_from_dict_roundtrip():
    g = make_genome()
    d = g.to_dict()
    g2 = AgentGenome.from_dict(d)
    assert g2 == g
    assert g2.key() == g.key()


def test_to_json_from_json_roundtrip():
    g = make_genome()
    payload = g.to_json()
    g2 = AgentGenome.from_json(payload)
    assert g2 == g
    # JSON is stable / sorted.
    assert AgentGenome.from_json(g2.to_json()).to_dict() == json.loads(payload)


def test_from_dict_missing_keys():
    with pytest.raises(ValueError):
        AgentGenome.from_dict({"planner_strategy": "cot"})


def test_comparison_and_ordering():
    a = make_genome()
    b = make_genome(reasoning_budget=64)
    assert a == make_genome()
    assert a != b
    assert (a < b) or (b < a)
    assert sorted([b, a]) == [a, b] or sorted([b, a]) == [b, a]


def test_replace_and_clone():
    g = make_genome()
    g2 = g.replace(reasoning_budget=64)
    assert g2.reasoning_budget == 64
    assert g.reasoning_budget == 32  # original unchanged
    c = g.clone()
    assert c == g and c is not g


def test_distance():
    a = make_genome()
    b = make_genome(memory_strategy="none")
    assert a.distance(a) == 0
    assert a.distance(b) == 1
