"""Real-LLM evaluation pipeline with cache (Phase 4-R1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.backend.base import LLMBackend, resolve_backend, get_env_key
from src.benchmark.alfworld_real import ALFWorldRealAdapter
from src.benchmark.base_adapter import BenchmarkAdapter
from src.evaluation.objective_evaluator import ObjectiveEvaluator
from src.agent.genome import AgentGenome
from src.runtime.agent_builder import AgentBuilder
from src.runtime.cache import EvaluationCache
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop


@dataclass
class RealLLMConfig:
    benchmark: str = "alfworld"
    n_tasks: int = 20
    backend: str = "auto"  # auto | mock | deepseek | openai
    seed: int = 0
    pop_size: int = 8
    n_generations: int = 5
    preference: Any = None
    budget_cap_usd: Optional[float] = 20.0
    cache_path: Optional[str] = None


class RealLLMPipeline:
    def __init__(
        self,
        config: Optional[RealLLMConfig] = None,
        *,
        backend: Optional[LLMBackend] = None,
        cache: Optional[EvaluationCache] = None,
        adapter: Optional[BenchmarkAdapter] = None,
    ) -> None:
        self.config = config or RealLLMConfig()
        self.cache = cache or EvaluationCache(self.config.cache_path)
        if backend is not None:
            self.backend = backend
        elif self.config.backend == "auto":
            if get_env_key("DEEPSEEK_API_KEY"):
                self.backend = resolve_backend("deepseek")
            elif get_env_key("OPENAI_API_KEY"):
                self.backend = resolve_backend("openai")
            else:
                self.backend = resolve_backend("mock")
        else:
            self.backend = resolve_backend(self.config.backend)

        self.builder = AgentBuilder(llm=self.backend)
        self.objectives = ObjectiveEvaluator()
        self.adapter = adapter or ALFWorldRealAdapter(
            n_tasks=self.config.n_tasks,
            seed=self.config.seed,
            backend=self.backend,
            cache=self.cache,
            budget_cap=self.config.budget_cap_usd,
        )

    def evaluate_genome(self, genome: AgentGenome) -> List[float]:
        agent = self.builder.build(genome, agent_id=0)
        episode = self.adapter.run(agent)
        return self.objectives.from_episode(episode)

    def as_evaluate_fn(self) -> Callable[[AgentGenome], Sequence[float]]:
        return self.evaluate_genome

    def cost_report(self) -> Dict[str, Any]:
        report = self.adapter.cost_report() if hasattr(self.adapter, "cost_report") else {}
        report["cache"] = self.cache.stats()
        return report


def run_real_llm_evolution(
    *,
    n_tasks: int = 20,
    pop_size: int = 8,
    n_generations: int = 5,
    seed: int = 0,
    backend: str = "auto",
    preference: Any = None,
    experience_mode: str = "robust_peem",
    use_adaptive: bool = True,
    cache_path: Optional[str] = None,
    budget_cap_usd: float = 20.0,
) -> Dict[str, Any]:
    pipe = RealLLMPipeline(
        RealLLMConfig(
            n_tasks=n_tasks,
            backend=backend,
            seed=seed,
            pop_size=pop_size,
            n_generations=n_generations,
            preference=preference,
            cache_path=cache_path,
            budget_cap_usd=budget_cap_usd,
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
    return {
        "pipeline": pipe,
        "loop": loop,
        "history": list(loop.history),
        "front": loop.pareto_front(),
        "front_fitness": [list(i.fitness_vector or []) for i in loop.pareto_front()],
        "final_hypervolume": loop.current_hypervolume(),
        "final_pareto_size": len(loop.pareto_front()),
        "cost_report": pipe.cost_report(),
        "backend": pipe.backend.name,
        "model": getattr(pipe.backend, "model", "unknown"),
    }
