"""Memory-aware evolutionary loop (Phase 2 / 2.5).

Phase 2: EvolutionArchive + MutationExperience + AdaptiveMutationController
Phase 2.5: ParetoExperience (PEEM) with composite mutation value + survival

Flow:
  Initialize -> Evaluate -> NSGA-III Selection
  -> Adaptive Mutation -> Evaluate Children
  -> Archive Update -> Experience/PEEM Update -> Repeat

Phase 0 NSGA-III and Phase 1 runtime APIs are reused unchanged.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.metrics import hypervolume, mutation_entropy
from src.evolution.adaptive_mutation import (
    AdaptiveMutationController,
    MutationOperatorRegistry,
    default_registry,
)
from src.evolution.archive import EvolutionArchive, EvolutionRecord
from src.evolution.credit_assignment import compute_credit
from src.evolution.experience import MutationExperience
from src.evolution.nsga3 import NSGA3
from src.evolution.operators import evolve_individual
from src.evolution.pareto_experience import ParetoExperience, PEEMConfig


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
    # Phase 2.5: "phase2" (success-rate) or "peem" (composite MV)
    experience_mode: str = "peem"
    decay: float = 0.35
    epsilon: float = 0.08


@dataclass
class MemoryEvolutionLoop:
    """Population evolution with Evolution / Pareto-aware Experience Memory."""

    evaluator: EvaluateFn
    config: MemoryEvolutionConfig = field(default_factory=MemoryEvolutionConfig)
    archive: EvolutionArchive = field(default_factory=EvolutionArchive)
    registry: MutationOperatorRegistry = field(default_factory=default_registry)

    individuals: List[Individual] = field(default_factory=list)
    generation: int = 0
    history: List[Dict] = field(default_factory=list)
    mutation_log: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.config.seed)
        self.nsga3 = NSGA3(
            n_objectives=self.config.n_objectives,
            divisions=self.config.divisions,
            seed=self.config.seed,
        )
        mode = (self.config.experience_mode or "peem").lower()
        if mode == "peem":
            self.experience: Union[ParetoExperience, MutationExperience] = ParetoExperience(
                PEEMConfig(decay=self.config.decay)
            )
        else:
            self.experience = MutationExperience()
        self.controller = AdaptiveMutationController(
            experience=self.experience,
            registry=self.registry,
            epsilon=self.config.epsilon,
        )
        self._pending: Dict[int, Tuple[Individual, Individual, str]] = {}

    # ------------------------------------------------------------------ #
    def initialize(self, genomes: Optional[Sequence[AgentGenome]] = None) -> List[Individual]:
        self.individuals = []
        self.generation = 0
        self.history = []
        self.mutation_log = []
        self._pending = {}
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
            self.mutation_log.append(mut_name)
        self._evaluate(children)
        return children

    def _ranks(self, inds: Sequence[Individual]) -> Dict[int, int]:
        rows = [list(i.fitness_vector or []) for i in inds]
        fronts = self.nsga3.sort_fronts(list(inds))
        rank = {}
        for fi, front in enumerate(fronts):
            for idx in front:
                rank[inds[idx].individual_id] = fi
        return rank

    def _update_from_transition(
        self,
        parent: Individual,
        child: Individual,
        mut_name: str,
        *,
        survived: bool,
        parent_rank: int,
        child_rank: int,
        pop_rows: Sequence[Sequence[float]],
    ) -> EvolutionRecord:
        parent_fit = list(parent.fitness_vector or [])
        child_fit = list(child.fitness_vector or [])
        credit = compute_credit(
            parent_fit,
            child_fit,
            population_front=pop_rows,
            parent_rank=parent_rank,
            child_rank=child_rank,
            survived=survived,
            seed=self.generation + 1,
        )
        rec = self.archive.record_transition(
            generation=self.generation + 1,
            parent_genome_id=str(parent.genome.key()),
            child_genome_id=str(child.genome.key()),
            mutation_type=mut_name,
            parent_objectives=parent_fit,
            child_objectives=child_fit,
            hv_delta=credit.hypervolume_gain,
            metadata={"mutation_value": credit.mutation_value},
        )
        # Attach Phase 2.5 fields (record_transition may not set them).
        rec.pareto_rank_change = credit.pareto_rank_change
        rec.hypervolume_contribution = credit.hypervolume_contribution
        rec.diversity_contribution = credit.diversity_contribution
        rec.survived_next_generation = bool(survived)
        rec.mutation_value = credit.mutation_value

        if isinstance(self.experience, ParetoExperience):
            self.experience.update(
                mut_name,
                parent_objectives=parent_fit,
                child_objectives=child_fit,
                population_front=pop_rows,
                parent_rank=parent_rank,
                child_rank=child_rank,
                survived=survived,
                generation=self.generation + 1,
            )
        else:
            self.experience.update(rec)
        return rec

    def next_generation(self) -> List[Individual]:
        parents = list(self.individuals)
        parent_rank = self._ranks(parents)
        parent_rows = [list(i.fitness_vector or []) for i in parents]
        children = self.make_children()
        child_rank = self._ranks(parents + children)
        combined = parents + children
        selected = self.nsga3.select(combined, self.config.pop_size)
        survived_ids = {id(i) for i in selected}

        by_id = {p.individual_id: p for p in parents}
        pop_rows = [list(i.fitness_vector or []) for i in selected]
        for child in children:
            pid = child.metadata.get("parent_id")
            parent = by_id.get(pid) if pid is not None else None
            if parent is None or not parent.has_fitness() or not child.has_fitness():
                continue
            self._update_from_transition(
                parent,
                child,
                str(child.metadata.get("mutation_type", "unknown")),
                survived=id(child) in survived_ids,
                parent_rank=parent_rank.get(parent.individual_id, 1),
                child_rank=child_rank.get(child.individual_id, 1),
                pop_rows=pop_rows,
            )

        self.individuals = selected
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
        return hypervolume(rows, n_samples=2048, seed=0) if rows else 0.0

    def mutation_type_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for t in self.mutation_log:
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _record_history(self) -> None:
        fronts = self.nsga3.sort_fronts(self.individuals)
        rows = [list(i.fitness_vector or []) for i in self.individuals]
        counts = self.mutation_type_counts()
        ent = mutation_entropy(list(counts.values())) if counts else 0.0
        self.history.append(
            {
                "generation": self.generation,
                "n_individuals": len(self.individuals),
                "n_non_dominated": len(fronts[0]) if fronts else 0,
                "hypervolume": hypervolume(rows, n_samples=512, seed=self.generation) if rows else 0.0,
                "archive_size": len(self.archive),
                "mutation_entropy": ent,
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
    experience_mode: str = "peem",
    divisions: int = 3,
    decay: float = 0.35,
) -> Dict[str, object]:
    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=n_offspring or pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        divisions=divisions,
        experience_mode=experience_mode,
        decay=decay,
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
        "mutation_counts": loop.mutation_type_counts(),
        "experience_mode": experience_mode,
    }
