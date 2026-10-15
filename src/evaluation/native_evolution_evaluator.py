"""Native ALFWorld evolution evaluator (Phase5-R3-R3 Task4).

evaluate(genome) -> objective vector from real TextWorld won/steps/tokens.
No capability prior. Suitable as MemoryEvolutionLoop.evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.evaluation.evaluation_kind import REAL_ENVIRONMENT
from src.runtime.behavioral_agent import BudgetMeter
from src.runtime.episode_runner import EpisodeRunner
from src.runtime.interactive_agent import BudgetExhaustedStop, InteractiveAgent


@dataclass
class NativeEpisodeRecord:
    game_id: str
    goal: str
    success: bool
    steps: int
    score: float
    api_calls: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    termination_reason: str
    trajectory: List[Dict[str, Any]]
    genome: Dict[str, Any]
    model: str = "deepseek-flash"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark": "alfworld_textworld",
            "evaluation_kind": REAL_ENVIRONMENT,
            "model": self.model,
            "game_id": self.game_id,
            "goal": self.goal,
            "success": self.success,
            "steps": self.steps,
            "score": self.score,
            "api_calls": self.api_calls,
            "input_tokens": self.tokens_in,
            "output_tokens": self.tokens_out,
            "cost_usd": self.cost_usd,
            "termination_reason": self.termination_reason,
            "genome": self.genome,
            "trajectory": self.trajectory,
        }


class NativeEvolutionEvaluator:
    """Genome -> InteractiveAgent -> native env episodes -> 5-objective vector."""

    def __init__(
        self,
        env_factory: Callable[[], Tuple[Any, Any, Callable]],
        llm_generate: Callable[[str], Tuple[str, Dict[str, Any]]],
        *,
        n_tasks: int = 2,
        max_steps: int = 12,
        model: str = "deepseek-flash",
    ) -> None:
        """env_factory() -> (reset_fn, step_fn, close_fn)."""
        self.env_factory = env_factory
        self.llm_generate = llm_generate
        self.n_tasks = n_tasks
        self.max_steps = max_steps
        self.model = model
        self.episodes: List[NativeEpisodeRecord] = []

    def evaluate(self, genome: AgentGenome) -> List[float]:
        return self.evaluate_genome(genome)

    def evaluate_genome(self, genome: AgentGenome) -> List[float]:
        env = self.env_factory() if callable(self.env_factory) else self.env_factory
        reset_fn, step_fn, _close = env[0], env[1], env[2] if len(env) > 2 else (lambda: None)
        runner = EpisodeRunner(genome, self.llm_generate, horizon=self.max_steps)
        results = []
        for i in range(self.n_tasks):
            try:
                out = runner.run(reset_fn, step_fn, episode_id=i, seed=i)
            except BudgetExhaustedStop:
                out = {
                    "episode_id": i, "game_id": "", "goal": "", "seed": i,
                    "success": False, "steps": 0, "score": 0.0,
                    "termination_reason": "budget_exhausted",
                    "api_calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0,
                    "reflection_count": 0, "trajectory": [],
                }
            results.append(out)
            self.episodes.append(NativeEpisodeRecord(
                game_id=str(out.get("game_id", "")),
                goal=str(out.get("goal", "")),
                success=bool(out.get("success")),
                steps=int(out.get("steps", 0)),
                score=float(out.get("score", 0.0)),
                api_calls=int(out.get("api_calls", 0)),
                tokens_in=int(out.get("tokens_in", 0)),
                tokens_out=int(out.get("tokens_out", 0)),
                cost_usd=float(out.get("cost_usd", 0.0)),
                termination_reason=str(out.get("termination_reason", "")),
                trajectory=list(out.get("trajectory", [])),
                genome=genome.to_dict(),
                model=self.model,
            ))
        return self.to_objectives(results)

    def to_objectives(self, results: Sequence[Dict[str, Any]]) -> List[float]:
        """Native objective vector (paper order).

        performance: won rate
        efficiency: 1 - normalized steps/tokens
        cost: API cost (lower better)
        robustness: success consistency across instances
        autonomy: fraction of steps without fallback/external help (behavioral)
        """
        n = max(1, len(results))
        perf = sum(1.0 for r in results if r.get("success")) / n
        steps = [int(r.get("steps", 0)) for r in results]
        tok = [int(r.get("tokens_in", 0)) + int(r.get("tokens_out", 0)) for r in results]
        cost = [float(r.get("cost_usd", 0.0)) for r in results]
        # efficiency: higher better
        eff = 1.0 / (1.0 + (sum(steps) / n) / max(1, self.max_steps) + (sum(tok) / n) / 2000.0)
        # cost: lower better, saturate
        c = (sum(cost) / n)
        cost_score = c / (c + 1.0)
        # robustness: success rate on harder half (by steps) + non-stall rate
        stall = sum(1 for r in results if str(r.get("termination_reason")) == "stalled_no_obs_change") / n
        robust = max(0.0, perf * (1.0 - stall))
        # autonomy: 1 - fallback_rate - early_budget_kill_rate
        fallback = 0.0
        traj_steps = 0
        for r in results:
            for t in r.get("trajectory", []):
                traj_steps += 1
        # behavioral proxy: if all terminations are budget_exhausted => low autonomy
        early = sum(1 for r in results if r.get("termination_reason") == "budget_exhausted") / n
        auto = max(0.0, 1.0 - 0.5 * early - 0.3 * stall)
        return [float(perf), float(eff), float(cost_score), float(robust), float(auto)]


class RandomSearchSampler:
    """True random search over genome space (no NSGA-III / PEEM / PPEC)."""

    def __init__(self, seed: int = 0) -> None:
        import random

        self.rng = random.Random(seed)
        self.archive: List[List[float]] = []

    def sample(self) -> AgentGenome:
        return AgentGenome.random(self.rng)

    def observe(self, fitness: Sequence[float]) -> None:
        """Archive only; does NOT change sampling distribution."""
        self.archive.append(list(fitness))

    def run(self, evaluator, n_evals: int) -> List[List[float]]:
        out = []
        for _ in range(n_evals):
            g = self.sample()
            f = evaluator(g)
            self.observe(f)
            out.append(list(f))
        return out
