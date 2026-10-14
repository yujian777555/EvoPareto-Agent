"""Memory-aware evolutionary loop (Phase 2 / 2.5 / 2.5-R1).

Phase 2:   EvolutionArchive + MutationExperience + AdaptiveMutationController
Phase 2.5: ParetoExperience (PEEM) with composite mutation value + survival
Phase 2.5-R1: rank-based Pareto credit, z-normalization, delayed credit,
              temperature-softmax mutation selection.

Flow:
  Initialize -> Evaluate -> NSGA-III Selection
  -> Adaptive Mutation -> Evaluate Children
  -> Robust Credit + Archive + PEEM Update
  -> Delayed Credit observe -> Repeat

Phase 0 NSGA-III and Phase 1 runtime APIs are reused unchanged.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evaluation.metrics import hypervolume, mutation_entropy
from src.evolution.adaptive_mutation import (
    AdaptiveMutationController,
    MutationOperatorRegistry,
    default_registry,
)
from src.evolution.archive import EvolutionArchive, EvolutionRecord
from src.evolution.credit_assignment import (
    CreditWeights,
    compute_credit,
    compute_robust_credit,
    robust_raw_components,
    apply_normalized_mv,
)
from src.evolution.delayed_credit import DelayedCreditBook, new_mutation_id
from src.evolution.experience import MutationExperience
from src.evolution.nsga3 import NSGA3
from src.evolution.normalization import GenerationNormalizer
from src.evolution.operators import evolve_individual
from src.evolution.pareto_experience import PEEMConfig, ParetoExperience
from src.evolution.pareto_credit import ParetoContributionEstimator
from src.evolution.preference import PreferenceVector, encode_preference, preference_satisfaction
from src.evolution.preference_controller import PreferenceController


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
    # "phase2" | "peem" | "robust_peem"
    experience_mode: str = "robust_peem"
    decay: float = 0.35
    epsilon: float = 0.08
    # Temperature annealing (R1)
    temperature: float = 1.0
    temperature_min: float = 0.2
    temperature_step: float = 0.02
    use_softmax: bool = True
    # Delayed credit
    delayed_horizon: int = 3
    use_delayed_credit: bool = True
    # Phase 3 preference
    preference: Any = None  # mode / dict / PreferenceVector / None
    preference_strength: float = 1.0


@dataclass
class MemoryEvolutionLoop:
    """Population evolution with Evolution / Pareto-aware / Robust PEEM memory."""

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
        # Phase 3: preference-aware selector when a preference is provided.
        self.preference = None
        self.pref_controller = None
        if self.config.preference is not None:
            self.preference = encode_preference(self.config.preference)
            self.pref_controller = PreferenceController(
                preference=self.preference,
                n_objectives=self.config.n_objectives,
                divisions=self.config.divisions,
                strength=self.config.preference_strength,
                seed=self.config.seed,
            )
            self.nsga3 = self.pref_controller.selector
        else:
            self.nsga3 = NSGA3(
                n_objectives=self.config.n_objectives,
                divisions=self.config.divisions,
                seed=self.config.seed,
            )
        mode = (self.config.experience_mode or "robust_peem").lower()
        if mode in ("peem", "robust_peem", "robust"):
            self.experience: Union[ParetoExperience, MutationExperience] = ParetoExperience(
                PEEMConfig(decay=self.config.decay)
            )
        else:
            self.experience = MutationExperience()
        self.controller = AdaptiveMutationController(
            experience=self.experience,
            registry=self.registry,
            epsilon=self.config.epsilon,
            temperature=self.config.temperature,
            temperature_min=self.config.temperature_min,
            temperature_step=self.config.temperature_step if self.config.use_softmax else 0.0,
            use_softmax=self.config.use_softmax,
        )
        self.delayed = DelayedCreditBook(horizon=self.config.delayed_horizon)
        self.pareto_est = ParetoContributionEstimator()
        self._pending_ids: Dict[int, str] = {}  # individual_id -> mutation_id

    @property
    def robust_mode(self) -> bool:
        return (self.config.experience_mode or "").lower() in ("robust_peem", "robust")

    # ------------------------------------------------------------------ #
    def initialize(self, genomes: Optional[Sequence[AgentGenome]] = None) -> List[Individual]:
        self.individuals = []
        self.generation = 0
        self.history = []
        self.mutation_log = []
        self._pending_ids = {}
        self.delayed = DelayedCreditBook(horizon=self.config.delayed_horizon)
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
        fronts = self.nsga3.sort_fronts(list(inds))
        rank = {}
        for fi, front in enumerate(fronts):
            for idx in front:
                rank[inds[idx].individual_id] = fi
        return rank

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

        # --- Batch robust credit with per-generation z-normalization ---
        pairs = []
        for child in children:
            pid = child.metadata.get("parent_id")
            parent = by_id.get(pid) if pid is not None else None
            if parent is None or not parent.has_fitness() or not child.has_fitness():
                continue
            pairs.append((parent, child, str(child.metadata.get("mutation_type", "unknown"))))

        if self.robust_mode and pairs:
            raw_rows = []
            comps = []
            for parent, child, mut_name in pairs:
                survived = id(child) in survived_ids
                raw = robust_raw_components(
                    parent.fitness_vector or [],
                    child.fitness_vector or [],
                    population=pop_rows,
                    survived=survived,
                    pareto_score=self.pareto_est.score_one(
                        parent.fitness_vector or [],
                        child.fitness_vector or [],
                        pop_rows,
                    ),
                )
                comps.append((parent, child, mut_name, survived, raw))
                raw_rows.append(raw.raw_row())

            norm = GenerationNormalizer()
            for row in raw_rows:
                norm.add_row(row)
            norm.fit()

            for (parent, child, mut_name, survived, raw), row in zip(comps, raw_rows):
                z = norm.transform_row(row)
                mut_id = new_mutation_id()
                bonus = 0.0
                if self.config.use_delayed_credit:
                    self.delayed.register(
                        mut_id,
                        generation=self.generation + 1,
                        mutation_type=mut_name,
                        child_objectives=child.fitness_vector or [],
                        immediate_mv=0.0,
                        genome_id=str(child.genome.key()),
                    )
                    bonus = self.delayed.delayed_bonus(mut_id)

                from src.evolution.credit_assignment import CreditWeights as CW

                w = CW().normalized()
                raw.improvement_norm = z["improvement"]
                raw.pareto_norm = row["pareto"]
                raw.diversity_norm = row["diversity"]
                raw.survival_norm = row["survival"]
                raw.mutation_value = (
                    w.alpha * z["improvement"]
                    + w.beta * row["pareto"]
                    + w.gamma * row["diversity"]
                    + w.delta * row["survival"]
                    + bonus
                )
                if self.config.use_delayed_credit:
                    self.delayed.records[mut_id]["immediate_mv"] = raw.mutation_value

                rec = self.archive.record_transition(
                    generation=self.generation + 1,
                    parent_genome_id=str(parent.genome.key()),
                    child_genome_id=str(child.genome.key()),
                    mutation_type=mut_name,
                    parent_objectives=list(parent.fitness_vector or []),
                    child_objectives=list(child.fitness_vector or []),
                    hv_delta=0.0,
                    metadata={"mutation_id": mut_id, "mutation_value": raw.mutation_value},
                )
                rec.pareto_rank_change = int(parent_rank.get(parent.individual_id, 1)) - int(
                    child_rank.get(child.individual_id, 1)
                )
                rec.hypervolume_contribution = 0.0
                rec.diversity_contribution = raw.diversity_score
                rec.survived_next_generation = bool(survived)
                rec.mutation_value = raw.mutation_value

                if isinstance(self.experience, ParetoExperience):
                    self.experience._absorb(mut_name, raw.mutation_value, raw.to_dict())
                else:
                    self.experience.update(rec)
                self._pending_ids[child.individual_id] = mut_id
        else:
            # Phase 2 / PEEM v1 path (compatible)
            for parent, child, mut_name in pairs:
                survived = id(child) in survived_ids
                self._update_from_transition(
                    parent,
                    child,
                    mut_name,
                    survived=survived,
                    parent_rank=parent_rank.get(parent.individual_id, 1),
                    child_rank=child_rank.get(child.individual_id, 1),
                    pop_rows=pop_rows,
                )

        # Delayed credit: observe new population
        if self.config.use_delayed_credit:
            self.delayed.observe_population(pop_rows, generation=self.generation + 1)
            self.delayed.step(generation=self.generation + 1)

        self.individuals = selected
        self.generation += 1
        self._record_history()
        return self.individuals

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

    def run(self, n_generations: int) -> List[Individual]:
        for _ in range(n_generations):
            self.next_generation()
        return self.individuals

    # ------------------------------------------------------------------ #
    def pareto_front(self) -> List[Individual]:
        return self.nsga3.pareto_front(self.individuals)

    def current_hypervolume(self) -> float:
        rows = [list(i.fitness_vector or []) for i in self.individuals]
        return hypervolume(rows, n_samples=1024, seed=0) if rows else 0.0

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
                "temperature": self.controller.current_temperature(),
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
    experience_mode: str = "robust_peem",
    divisions: int = 3,
    decay: float = 0.35,
    temperature: float = 1.0,
    temperature_min: float = 0.2,
    temperature_step: float = 0.02,
    use_softmax: bool = True,
    use_delayed_credit: bool = True,
    preference: Any = None,
    preference_strength: float = 1.0,
) -> Dict[str, object]:
    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=n_offspring or pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        divisions=divisions,
        experience_mode=experience_mode,
        decay=decay,
        temperature=temperature,
        temperature_min=temperature_min,
        temperature_step=temperature_step,
        use_softmax=use_softmax,
        use_delayed_credit=use_delayed_credit,
        preference=preference,
        preference_strength=preference_strength,
    )
    loop = MemoryEvolutionLoop(evaluator=evaluator, config=cfg)
    loop.initialize()
    loop.run(n_generations)
    pref_scores = []
    if loop.preference is not None:
        for ind in loop.individuals:
            if ind.has_fitness():
                pref_scores.append(preference_satisfaction(ind.fitness_vector or [], loop.preference))
    return {
        "loop": loop,
        "history": list(loop.history),
        "front": loop.pareto_front(),
        "archive": loop.archive,
        "experience": loop.experience,
        "delayed": loop.delayed,
        "final_hypervolume": loop.current_hypervolume(),
        "final_pareto_size": len(loop.pareto_front()),
        "mutation_probs": loop.controller.probability_distribution(),
        "mutation_counts": loop.mutation_type_counts(),
        "experience_mode": experience_mode,
        "preference": loop.preference.as_dict() if loop.preference else None,
        "preference_satisfaction": (sum(pref_scores) / len(pref_scores)) if pref_scores else None,
    }
