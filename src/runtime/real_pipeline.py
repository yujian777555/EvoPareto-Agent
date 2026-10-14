"""Real-benchmark evaluation pipeline (Phase 4).

Genome → AgentBuilder(+LLM backend) → BenchmarkAdapter → TaskResults
      → ObjectiveEvaluator → objective vector → PEEM-PPEC loop.

Algorithm modules (NSGA-III / PEEM / PPEC) are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.backend.base import LLMBackend, MockLLMBackend, resolve_backend
from src.benchmark.base_adapter import BenchmarkAdapter
from src.benchmark.alfworld import ALFWorldAdapter
from src.benchmark.webshop import WebShopAdapter
from src.evaluation.objective_evaluator import ObjectiveEvaluator
from src.agent.genome import AgentGenome
from src.runtime.agent_builder import AgentBuilder
from src.evolution.memory_evolution import MemoryEvolutionLoop, MemoryEvolutionConfig


@dataclass
class RealEvalConfig:
    benchmark: str = "alfworld"  # alfworld | webshop
    n_tasks: int = 10
    backend: str = "mock"  # mock | openai | deepseek
    seed: int = 0
    difficulty_scale: float = 1.0


class RealBenchmarkPipeline:
    """Evaluate genomes on a real/simulated agent benchmark."""

    def __init__(
        self,
        config: Optional[RealEvalConfig] = None,
        *,
        adapter: Optional[BenchmarkAdapter] = None,
        backend: Optional[LLMBackend] = None,
    ) -> None:
        self.config = config or RealEvalConfig()
        self.backend = backend or resolve_backend(self.config.backend)
        self.builder = AgentBuilder(llm=self.backend)
        self.objectives = ObjectiveEvaluator()
        self.adapter = adapter or self._make_adapter()

    def _make_adapter(self) -> BenchmarkAdapter:
        cfg = self.config
        kind = cfg.benchmark.lower()
        if kind == "alfworld":
            return ALFWorldAdapter(
                n_tasks=cfg.n_tasks, seed=cfg.seed, backend=self.backend,
                difficulty_scale=cfg.difficulty_scale,
            )
        if kind == "webshop":
            return WebShopAdapter(
                n_tasks=cfg.n_tasks, seed=cfg.seed, backend=self.backend,
                difficulty_scale=cfg.difficulty_scale,
            )
        raise ValueError(f"unknown benchmark: {cfg.benchmark!r}")

    def evaluate_genome(self, genome: AgentGenome) -> List[float]:
        agent = self.builder.build(genome, agent_id=0)
        episode = self.adapter.run(agent)
        return self.objectives.from_episode(episode)

    def evaluate_genome_recorded(self, genome: AgentGenome):
        agent = self.builder.build(genome, agent_id=0)
        episode, records = self.adapter.run_recorded(agent)
        vec = self.objectives.from_episode(episode)
        return vec, episode, records

    def as_evaluate_fn(self) -> Callable[[AgentGenome], Sequence[float]]:
        return self.evaluate_genome

    def summary(self) -> Dict[str, Any]:
        return {
            "benchmark": self.adapter.name,
            "n_tasks": self.adapter.n_tasks,
            "backend": self.backend.name,
            "model": getattr(self.backend, "model", "unknown"),
        }


def run_real_agent_evolution(
    *,
    benchmark: str = "alfworld",
    n_tasks: int = 10,
    backend: str = "mock",
    pop_size: int = 20,
    n_generations: int = 8,
    seed: int = 42,
    preference: Any = None,
    experience_mode: str = "robust_peem",
    use_adaptive: bool = True,
    difficulty_scale: float = 1.0,
) -> Dict[str, Any]:
    """Full PEEM-PPEC loop on a real/simulated agent benchmark."""
    pipe = RealBenchmarkPipeline(
        RealEvalConfig(
            benchmark=benchmark,
            n_tasks=n_tasks,
            backend=backend,
            seed=seed,
            difficulty_scale=difficulty_scale,
        )
    )
    cfg = MemoryEvolutionConfig(
        pop_size=pop_size,
        n_offspring=pop_size,
        seed=seed,
        use_adaptive=use_adaptive,
        experience_mode=experience_mode,
        preference=preference,
    )
    loop = MemoryEvolutionLoop(evaluator=pipe.as_evaluate_fn(), config=cfg)
    loop.initialize()
    loop.run(n_generations)

    # Re-evaluate final population with trajectory recording for artifacts.
    records = []
    for ind in loop.individuals:
        vec, episode, recs = pipe.evaluate_genome_recorded(ind.genome)
        records.extend(r.to_dict() for r in recs)

    front = loop.pareto_front()
    return {
        "pipeline": pipe,
        "loop": loop,
        "history": list(loop.history),
        "front": front,
        "front_genomes": [i.genome.to_dict() for i in front],
        "front_fitness": [list(i.fitness_vector or []) for i in front],
        "episodes": records,
        "final_hypervolume": loop.current_hypervolume(),
        "final_pareto_size": len(front),
        "benchmark": pipe.summary(),
        "preference": loop.preference.as_dict() if loop.preference else None,
    }
