"""Memory-aware evolutionary loop (Phase 2).

Flow:
  Initialize -> Evaluate -> NSGA-III Selection
  -> Adaptive Mutation -> Evaluate Children
  -> Archive Update -> Experience Update -> Repeat

Phase 0 NSGA-III and Phase 1 runtime APIs are reused unchanged.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.metrics import hypervolume, pareto_front_size
from src.evolution.adaptive_mutation import (
    AdaptiveMutationController,
    MutationOperatorRegistry,
    default_registry,
)
from src.evolution.archive import EvolutionArchive, EvolutionRecord
from src.evolution.experience import MutationExperience
from src.evolution.nsga3 import NSGA3
from src.evolution.operators import evolve_individual, mutate_genome


EvaluateFn = Callable[[AgentGenome], Sequence[float]]


@dataclass
class MemoryEvolutionConfig:
    pop_size: int = 30
    n_offspring: int = 30
    n_objectives: int = 5
    divisions: int = 3
    seed: int = 42
    n_mutations: int = 1
    mutation_rate: float = 0.85
    use_adaptive: bool = True


@dataclass
class MemoryEvolutionLoop:
    """Population evolution with Evolution Experience Memory."""

    evaluator: EvaluateFn
    config: MemoryEvolutionConfig = field(default_factory=MemoryEvolutionConfig)
    archive: EvolutionArchive = field(default_factory=EvolutionArchive)
    experience: MutationExperience = field(default_factory=MutationExperience)
    registry: MutationOperatorRegistry = field(default_factory=default_registry)

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
        self.controller = AdaptiveMutationController(
            experience=self.experience,
            registry=self.registry,
        )

    # ------------------------------------------------------------------ #
    def initialize(self, genomes: Optional[Sequence[AgentGenome]] = None) -> List[Individual]:
        self.individuals = []
        self.generation = 0
        self.history = []
        cfg = self.config
        if genomes is not None:
            for g in genomes:
                self.individuals.append(Individual(genome=g.clone(), generation=0))
        while len(self.individuals) < cfg.pop_size:
            self.individuals.append(
                Individual(genome=AgentGenome.random(self.rng), generation=0)
            )
        self.individuals = self.individuals[: cfg.pop_size]
        self._evaluate(self.individuals)
        self._record_history()
        return self.individuals

    def _evaluate(self, inds: Sequence[Individual]) -> None:
        for ind in inds:
            if not ind.has_fitness():
                ind.set_fitness(self.evaluator(ind.genome))

    # ------------------------------------------------------------------ #
    # Children via adaptive (or random) mutation
    # ------------------------------------------------------------------ #
    def make_children(self) -> List[Individual]:
        cfg = self.config
        children: List[Individual] = []
        parents = list(self.individuals)
        if not parents:
            return []
        while len(children) < cfg.n_offspring:
            parent = self.rng.choice(parents)
            if cfg.use_adaptive:
                child, used = self.controller.mutate_individual(
                    parent,
                    self.rng,
                    generation=self.generation + 1,
                    n_mutations=cfg.n_mutations,
                    rate=cfg.mutation_rate,
                )
                mut_name = "+".join(used) if used else "none"
            else:
                child = evolve_individual(
                    parent,
                    self.rng,
                    generation=self.generation + 1,
                    n_mutations=cfg.n_mutations,
                    mutation_rate=cfg.mutation_rate,
                )
                mut_name = "random"
            child.metadata["mutation_type"] = mut_name
            children.append(child)
        self._evaluate(children)
        return children

    def _update_archive_from(
        self,
        parents: Sequence[Individual],
        children: Sequence[Individual],
    ) -> List[EvolutionRecord]:
        records: List[EvolutionRecord] = []
        # Match each child to its parent via metadata when available.
        by_id = {p.individual_id: p for p in parents}
        for child in children:
            pid = child.metadata.get("parent_id")
            parent = by_id.get(pid) if pid is not None else None
            if parent is None or not parent.has_fitness() or not child.has_fitness():
                continue
            rec = self.archive.record_transition(
                generation=self.generation + 1,
                parent_genome_id=str(parent.genome.key()),
                child_genome_id=str(child.genome.key()),
                mutation_type=str(child.metadata.get("mutation_type", "unknown")),
                parent_objectives=list(parent.fitness_vector or []),
                child_objectives=list(child.fitness_vector or []),
            )
            records.append(rec)
            self.experience.update(rec)
        return records

    # ------------------------------------------------------------------ #
    def next_generation(self) -> List[Individual]:
        parents = list(self.individuals)
        children = self.make_children()
        self._update_archive_from(parents, children)
        combined = parents + children
        self.individuals = self.nsga3.select(combined, self.config.pop_size)
        self.generation += 1
        self._record_history()
        return self.individuals

    def run(self, n_generations: int) -> List[Individual]:
        for _ in range(n_generations):
            self.next_generation()
        return self.individuals

    # ------------------------------------------------------------------ #
    def pareto_front(self) -> List[Individual]:
        return self.nsga3.pareto_front(self.individuals)

    def current_hypervolume(self) -> float:
        rows = [list(i.fitness_vector or []) for i in self.individuals]
        return hypervolume(rows, n_samples=4096, seed=0) if rows else 0.0

    def _record_history(self) -> None:
        fronts = self.nsga3.sort_fronts(self.individuals)
        rows = [list(i.fitness_vector or []) for i in self.individuals]
        self.history.append(
            {
                "generation": self.generation,
                "n_individuals": len(self.individuals),
                "n_non_dominated": len(fronts[0]) if fronts else 0,
                "hypervolume": hypervolume(rows, n_samples=2048, seed=self.generation) if rows else 0.0,
                "archive_size": len(self.archive),
                "mutation_probs": (
                    self.controller.probability_distribution()
                    if self.config.use_adaptive
                    else {}
                ),
            }
        )


def run_memory_evolution(
    evaluator: EvaluateFn,
    *,
    pop_size: int = 30,
    n_generations: int = 8,
    n_offspring: Optional[int] = None,
    seed: int = 42,
    use_adaptive: bool = True,
    divisions: int = 3,
) -> Dict[str, object]:
    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=n_offspring or pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        divisions=divisions,
    )
    loop = MemoryEvolutionLoop(evaluator=evaluator, config=cfg)
    loop.initialize()
    loop.run(n_generations)
    return {
        "loop": loop,
        "history": list(loop.history),
        "front": loop.pareto_front(),
        "archive": loop.archive,
        "experience": loop.experience,
        "final_hypervolume": loop.current_hypervolume(),
        "final_pareto_size": len(loop.pareto_front()),
        "mutation_probs": loop.controller.probability_distribution(),
    }
