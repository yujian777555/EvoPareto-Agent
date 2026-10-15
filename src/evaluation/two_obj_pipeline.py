"""2D objective native evaluator wrapper (Phase5-R3-R5-R1 Task E)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from src.agent.genome import AgentGenome
from src.evaluation.objective_spec import SPEC_2, SPEC_5, ObjectiveSpec, get_spec
from src.evaluation.native_evolution_evaluator import NativeEvolutionEvaluator
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop


class TwoObjNativeEvaluator:
    """Wraps native episodes into candidate_2obj fitness [success, cost]."""

    version = "candidate_2obj"

    def __init__(self, native: NativeEvolutionEvaluator) -> None:
        self.native = native
        self.spec = SPEC_2

    def evaluate(self, genome: AgentGenome) -> List[float]:
        # Collect raw episodes via native evaluator then map to 2D.
        # Native evaluate returns 5-obj; we instead rebuild from episodes.
        self.native.evaluate_genome(genome)
        eps = self.native.episodes[-self.native.n_tasks:]
        success = sum(1.0 for e in eps if e.success) / max(1, len(eps))
        cost = sum(e.cost_usd for e in eps) / max(1, len(eps))
        vec = [success, cost]
        self.spec.validate_vector(vec)
        return vec


def run_2d_evolution(
    evaluator: Callable[[AgentGenome], Sequence[float]],
    *,
    pop_size: int = 8,
    generations: int = 2,
    seed: int = 0,
    preference: Optional[str] = None,
    use_peem: bool = True,
    objective_version: str = "candidate_2obj",
) -> Dict[str, Any]:
    spec = get_spec(objective_version)
    if spec.n != 2:
        raise ValueError("run_2d_evolution requires candidate_2obj")

    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        n_objectives=2,
        use_adaptive=use_peem,
        experience_mode="robust_peem" if use_peem else "phase2",
        preference=preference,
        divisions=4,
    )
    loop = MemoryEvolutionLoop(evaluator=evaluator, config=cfg)
    # Do NOT override selector here — MemoryEvolutionLoop installs
    # PreferenceAware/NSGA3 with maximize=(True, False) when n_objectives==2.
    # Force maximize mask on the already-constructed selector.
    if hasattr(loop.nsga3, "config"):
        loop.nsga3.config.maximize = spec.maximize
    loop.initialize()
    loop.run(generations)
    front = loop.pareto_front()
    return {
        "objective_version": objective_version,
        "spec": {"names": list(spec.names), "maximize": list(spec.maximize)},
        "pop_size": pop_size,
        "generations": generations,
        "front": [list(i.fitness_vector or []) for i in front],
        "population": [list(i.fitness_vector or []) for i in loop.individuals],
        "history": loop.history,
    }
