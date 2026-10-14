"""Individual serialization tests."""

from src.agent.genome import AgentGenome
from src.agent.individual import Individual


def make_ind():
    g = AgentGenome(
        planner_strategy="cot",
        memory_strategy="episodic",
        reflection_strategy="self_critique",
        tool_policy="balanced",
        reasoning_budget=32,
    )
    return Individual(genome=g, fitness_vector=[0.5, 0.5, 0.2, 0.6, 0.7], generation=3)


def test_individual_roundtrip():
    ind = make_ind()
    d = ind.to_dict()
    ind2 = Individual.from_dict(d)
    assert ind2.genome == ind.genome
    assert ind2.fitness_vector == ind.fitness_vector
    assert ind2.generation == ind.generation
    assert ind2.individual_id == ind.individual_id


def test_individual_json_roundtrip():
    ind = make_ind()
    payload = ind.to_json()
    ind2 = Individual.from_json(payload)
    assert ind2.to_dict() == ind.to_dict()


def test_individual_clone_reset_id():
    ind = make_ind()
    c = ind.clone(reset_id=True)
    assert c.individual_id != ind.individual_id
    assert c.genome == ind.genome


def test_individual_without_fitness():
    g = AgentGenome.random(__import__("random").Random(0))
    ind = Individual(genome=g)
    assert not ind.has_fitness()
    ind.set_fitness([0.1, 0.2, 0.3, 0.4, 0.5])
    assert ind.has_fitness()
    assert ind.n_objectives == 5
