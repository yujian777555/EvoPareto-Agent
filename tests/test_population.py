"""Population manager tests."""

import random

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.evaluator import ToyEvaluator
from src.evolution.population import Population, PopulationConfig
from src.utils.pareto import dominates_max, pareto_mask_max


def test_population_initialize_and_size():
    evaluator = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=10, n_offspring=10, seed=0)
    pop = Population(evaluator=evaluator.evaluate, config=cfg)
    inds = pop.initialize()
    assert len(inds) == 10
    assert all(ind.has_fitness() for ind in inds)
    assert pop.generation == 0
    assert len(pop.history) == 1


def test_population_add_evaluates():
    evaluator = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=5, n_offspring=5, seed=1)
    pop = Population(evaluator=evaluator.evaluate, config=cfg)
    pop.initialize()
    extra = Individual(genome=AgentGenome.random(random.Random(99)))
    pop.add(extra)
    assert extra.has_fitness()
    assert len(extra.fitness_vector) == 5


def test_population_select_returns_k():
    evaluator = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=8, n_offspring=8, seed=2)
    pop = Population(evaluator=evaluator.evaluate, config=cfg)
    pop.initialize()
    pool = pop.individuals + pop.offspring()
    chosen = pop.select(pool, k=8)
    assert len(chosen) == 8
    assert all(ind.has_fitness() for ind in chosen)


def test_next_generation_maintains_size_and_progress():
    evaluator = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=12, n_offspring=12, seed=3)
    pop = Population(evaluator=evaluator.evaluate, config=cfg)
    pop.initialize()
    for _ in range(5):
        pop.next_generation()
    assert len(pop.individuals) == 12
    assert pop.generation == 5
    assert len(pop.history) == 6  # init + 5 generations


def test_population_pareto_front_non_dominated():
    evaluator = ToyEvaluator(noise_scale=0.0)
    cfg = PopulationConfig(pop_size=15, n_offspring=15, seed=4)
    pop = Population(evaluator=evaluator.evaluate, config=cfg)
    pop.initialize()
    pop.run(4)
    front = pop.pareto_front()
    assert len(front) >= 1
    rows = [ind.fitness_vector for ind in front]
    # No member of the front dominates another under maximization semantics.
    for i in range(len(rows)):
        for j in range(len(rows)):
            if i == j:
                continue
            assert not dominates_max(rows[i], rows[j])
    mask = pareto_mask_max(rows)
    assert all(mask)


def test_deterministic_with_same_seed():
    def run(seed: int):
        evaluator = ToyEvaluator(noise_scale=0.0)
        cfg = PopulationConfig(pop_size=10, n_offspring=10, seed=seed)
        pop = Population(evaluator=evaluator.evaluate, config=cfg)
        pop.initialize()
        pop.run(3)
        return sorted(
            tuple(ind.fitness_vector) for ind in pop.individuals
        )

    assert run(42) == run(42)
