"""End-to-end Phase 1 evaluation pipeline.

Genome -> AgentBuilder -> Agent -> Benchmark -> TaskResults
      -> ObjectiveEvaluator -> objective vector -> NSGA-III (Population)

Phase 0 NSGA-III / Population contracts are reused unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.benchmark.base import Benchmark
from src.benchmark.mock_benchmark import MockBenchmark
from src.evaluation.objective_evaluator import ObjectiveEvaluator
from src.evolution.population import Population, PopulationConfig
from src.runtime.agent_builder import AgentBuilder


@dataclass
class AgentEvaluationPipeline:
    """Wires builder + benchmark + objective evaluator into EvaluateFn."""

    benchmark: Benchmark
    builder: AgentBuilder
    objective_evaluator: ObjectiveEvaluator
    seed: int = 0

    def evaluate_genome(self, genome: AgentGenome) -> List[float]:
        agent = self.builder.build(genome, agent_id=0)
        episode = self.benchmark.evaluate(agent)
        return self.objective_evaluator.from_episode(episode)

    def as_evaluate_fn(self) -> Callable[[AgentGenome], Sequence[float]]:
        return self.evaluate_genome

    def evaluate_individual(self, individual: Individual) -> List[float]:
        values = self.evaluate_genome(individual.genome)
        individual.set_fitness(values)
        return values


def build_default_pipeline(
    *,
    n_tasks: int = 12,
    seed: int = 0,
    benchmark: Optional[Benchmark] = None,
) -> AgentEvaluationPipeline:
    return AgentEvaluationPipeline(
        benchmark=benchmark if benchmark is not None else MockBenchmark(n_tasks=n_tasks, seed=seed),
        builder=AgentBuilder(),
        objective_evaluator=ObjectiveEvaluator(),
        seed=seed,
    )


def run_agent_evolution(
    *,
    pop_size: int = 30,
    n_generations: int = 8,
    n_tasks: int = 12,
    divisions: int = 3,
    seed: int = 42,
) -> dict:
    """Full loop used by the Phase 1 demo; returns artifacts + population."""
    pipeline = build_default_pipeline(n_tasks=n_tasks, seed=seed)
    cfg = PopulationConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        n_objectives=5,
        divisions=divisions,
        seed=seed,
    )
    pop = Population(evaluator=pipeline.as_evaluate_fn(), config=cfg)
    pop.initialize()
    pop.run(n_generations)

    front = pop.pareto_front()
    return {
        "population": pop,
        "pipeline": pipeline,
        "front": front,
        "history": list(pop.history),
    }
