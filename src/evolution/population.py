"""Population manager for NSGA-III based agent configuration search."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evolution.nsga3 import NSGA3, non_dominated_sort
from src.evolution.operators import crossover, evolve_individual


EvaluateFn = Callable[[AgentGenome], Sequence[float]]


@dataclass
class PopulationConfig:
    pop_size: int = 40
    n_offspring: int = 40
    n_objectives: int = 5
    divisions: int = 3
    seed: int = 42
    n_mutations: int = 1
    mutation_rate: float = 0.85
    crossover_rate: float = 0.5


@dataclass
class Population:
    """Maintains individuals, evaluates genomes, and advances generations."""

    evaluator: EvaluateFn
    config: PopulationConfig = field(default_factory=PopulationConfig)
    individuals: List[Individual] = field(default_factory=list)
    generation: int = 0
    history: List[Dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.config.seed)
        self.nsga3 = NSGA3(
            n_objectives=self.config.n_objectives,
            divisions=self.config.divisions,
            seed=self.config.seed,
        )

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #
    def initialize(
        self,
        genomes: Optional[Sequence[AgentGenome]] = None,
        *,
        random_init: bool = True,
    ) -> List[Individual]:
        """Create the initial population and evaluate it."""
        self.individuals = []
        self.generation = 0
        self.history = []

        if genomes is not None:
            for g in genomes:
                self.individuals.append(
                    Individual(genome=g.clone(), generation=0)
                )

        if random_init:
            while len(self.individuals) < self.config.pop_size:
                self.individuals.append(
                    Individual(
                        genome=AgentGenome.random(self.rng),
                        generation=0,
                    )
                )
        elif len(self.individuals) < self.config.pop_size:
            raise ValueError(
                "genomes shorter than pop_size and random_init=False"
            )

        # Keep exactly pop_size individuals.
        self.individuals = self.individuals[: self.config.pop_size]
        self.evaluate_all(self.individuals)
        self._record_history()
        return self.individuals

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    def evaluate_all(self, individuals: Iterable[Individual]) -> None:
        for ind in individuals:
            if not ind.has_fitness():
                values = self.evaluator(ind.genome)
                ind.set_fitness(values)

    # ------------------------------------------------------------------ #
    # Mutation / selection hooks
    # ------------------------------------------------------------------ #
    def add(self, individual: Individual) -> None:
        if not individual.has_fitness():
            self.evaluate_all([individual])
        self.individuals.append(individual)

    def select(
        self,
        candidates: Sequence[Individual],
        k: Optional[int] = None,
    ) -> List[Individual]:
        """NSGA-III environmental selection from a candidate pool."""
        target = self.config.pop_size if k is None else k
        return self.nsga3.select(list(candidates), target)

    def offspring(self) -> List[Individual]:
        """Generate `n_offspring` children from the current population."""
        cfg = self.config
        parents = list(self.individuals)
        if not parents:
            return []

        children: List[Individual] = []
        while len(children) < cfg.n_offspring:
            if len(parents) >= 2 and self.rng.random() < cfg.crossover_rate:
                p1, p2 = self.rng.sample(parents, 2)
                g1, g2 = crossover(
                    p1.genome, p2.genome, self.rng, rate=cfg.crossover_rate
                )
                for g in (g1, g2):
                    child = Individual(
                        genome=g,
                        generation=self.generation + 1,
                        metadata={
                            "parents": [p1.individual_id, p2.individual_id],
                            "operator": "crossover+mutation",
                        },
                    )
                    if self.rng.random() < cfg.mutation_rate:
                        from src.evolution.operators import mutate_genome

                        child.genome = mutate_genome(
                            child.genome, self.rng, n_mutations=cfg.n_mutations
                        )
                    children.append(child)
            else:
                p1 = self.rng.choice(parents)
                children.append(
                    evolve_individual(
                        p1,
                        self.rng,
                        generation=self.generation + 1,
                        n_mutations=cfg.n_mutations,
                        mutation_rate=cfg.mutation_rate,
                    )
                )
            if len(children) >= cfg.n_offspring:
                break

        children = children[: cfg.n_offspring]
        self.evaluate_all(children)
        return children

    def next_generation(self) -> List[Individual]:
        """(μ+λ) NSGA-III generation advance."""
        children = self.offspring()
        combined = list(self.individuals) + children
        self.individuals = self.select(combined, self.config.pop_size)
        self.generation += 1
        self._record_history()
        return self.individuals

    def run(self, n_generations: int) -> List[Individual]:
        for _ in range(n_generations):
            self.next_generation()
        return self.individuals

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def pareto_front(self) -> List[Individual]:
        return self.nsga3.pareto_front(self.individuals)

    def fitness_matrix(self) -> List[List[float]]:
        return [list(ind.fitness_vector or []) for ind in self.individuals]

    def _record_history(self) -> None:
        fronts = non_dominated_sort(self.fitness_matrix())
        n_nd = len(fronts[0]) if fronts else 0
        self.history.append(
            {
                "generation": self.generation,
                "n_individuals": len(self.individuals),
                "n_non_dominated": n_nd,
                "fitness_sum": [
                    sum(row[j] for row in self.fitness_matrix())
                    for j in range(self.config.n_objectives)
                ],
            }
        )
