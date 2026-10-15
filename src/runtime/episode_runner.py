"""Episode lifecycle: fresh state per episode (Phase5-R3-R3 Task1)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.runtime.behavioral_agent import BudgetMeter, MemoryStore
from src.runtime.interactive_agent import InteractiveAgent


@dataclass
class EpisodeState:
    episode_id: int
    game_id: str
    goal: str
    seed: int
    memory: MemoryStore
    budget: BudgetMeter
    reflection_count: int = 0
    parse_failures: int = 0
    repeated_actions: int = 0
    no_obs_change: int = 0
    termination_reason: str = "running"
    api_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    env_steps: int = 0
    trajectory: List[Dict[str, Any]] = field(default_factory=list)


class EpisodeRunner:
    """Runs one episode with fully isolated agent state."""

    def __init__(
        self,
        genome: AgentGenome,
        llm_generate: Callable[[str], Tuple[str, Dict[str, Any]]],
        *,
        horizon: int = 20,
    ) -> None:
        """llm_generate(prompt) -> (text, usage dict with tokens/cost)."""
        self.genome = genome
        self.llm_generate = llm_generate
        self.horizon = horizon

    def make_agent(self) -> InteractiveAgent:
        """Fresh InteractiveAgent (new MemoryStore + BudgetMeter)."""
        def _gen(prompt: str) -> str:
            text, _ = self.llm_generate(prompt)
            return text

        agent = InteractiveAgent(self.genome, _gen, horizon=self.horizon)
        return agent

    def extract_goal(self, observation: str, infos: Dict[str, Any]) -> str:
        """Goal from env observation/metadata — never gold trajectory."""
        for key in ("goal", "task_goal", "extra.goal"):
            if isinstance(infos, dict) and infos.get(key):
                v = infos[key]
                return str(v[0] if isinstance(v, (list, tuple)) else v)
        m = re.search(r"Your task is to (.+)", observation or "")
        if m:
            return m.group(1).strip()
        # ALFWorld TW often embeds task in first lines
        for line in (observation or "").splitlines():
            if "task is to" in line.lower():
                return line.strip()
        return ""

    def run(self, env_reset, env_step, *, episode_id: int = 0, seed: int = 0) -> Dict[str, Any]:
        """env_reset() -> (obs, infos); env_step(action) -> (obs, scores, dones, infos).

        episode_id is forwarded to env_reset(episode_index=...) when supported
        so each episode can load a distinct native game instance.
        """
        try:
            obs, infos = env_reset(episode_index=episode_id)
        except TypeError:
            obs, infos = env_reset()
        o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
        game_id = ""
        if isinstance(infos, dict):
            gf = infos.get("extra.gamefile") or infos.get("gamefile")
            if gf:
                game_id = str(gf[0] if isinstance(gf, (list, tuple)) else gf)
        goal = self.extract_goal(str(o0), infos if isinstance(infos, dict) else {})
        agent = self.make_agent()
        state = EpisodeState(
            episode_id=episode_id,
            game_id=game_id,
            goal=goal,
            seed=seed,
            memory=agent.memory,
            budget=agent.budget,
        )

        def usage_wrap(prompt: str) -> str:
            raw = self.llm_generate(prompt)
            if isinstance(raw, tuple) and len(raw) >= 2:
                text, usage = raw[0], raw[1]
            else:
                text, usage = raw, {}
            state.api_calls += int(usage.get("calls", 1))
            state.tokens_in += int(usage.get("tokens_in", 0))
            state.tokens_out += int(usage.get("tokens_out", 0))
            state.cost_usd += float(usage.get("cost", 0.0))
            return text

        # rebind agent LLM to usage-aware wrapper
        agent.llm_generate = usage_wrap

        success = False
        score = 0.0
        last_obs = str(o0)
        for t in range(self.horizon):
            if not agent.budget.can_step():
                state.termination_reason = "budget_exhausted"
                break
            adm: List[str] = []
            if isinstance(infos, dict):
                a = infos.get("admissible_commands")
                if a:
                    adm = list(a[0]) if isinstance(a[0], (list, tuple)) else list(a)
            action = agent.select_action(str(o0), adm, goal=goal)
            state.env_steps += 1
            if action == "look" and state.termination_reason == "budget_exhausted":
                break
            out = env_step([action])
            obs, scores, dones, infos = out[0], out[1], out[2], out[3]
            o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
            score = scores[0] if isinstance(scores, (list, tuple)) else scores
            done = dones[0] if isinstance(dones, (list, tuple)) else dones
            won = False
            if isinstance(infos, dict):
                w = infos.get("won")
                if w is not None:
                    won = bool(w[0] if isinstance(w, (list, tuple)) else w)
            if str(o0) == last_obs:
                state.no_obs_change += 1
            else:
                state.no_obs_change = 0
            last_obs = str(o0)
            state.trajectory.append({
                "t": t, "action": action, "obs": str(o0)[:240],
                "score": float(score), "won": won, "done": bool(done),
            })
            if won or done:
                success = won
                state.termination_reason = "won" if won else "env_done"
                break
            if state.no_obs_change >= 6:
                state.termination_reason = "stalled_no_obs_change"
                break
        else:
            if state.termination_reason == "running":
                state.termination_reason = "max_steps"

        state.reflection_count = agent.reflection_count
        return {
            "episode_id": episode_id,
            "game_id": state.game_id,
            "goal": state.goal,
            "seed": seed,
            "success": bool(success),
            "steps": state.env_steps,
            "score": float(score),
            "termination_reason": state.termination_reason,
            "api_calls": state.api_calls,
            "tokens_in": state.tokens_in,
            "tokens_out": state.tokens_out,
            "cost_usd": state.cost_usd,
            "reflection_count": state.reflection_count,
            "memory_reads": agent.memory.reads,
            "memory_writes": agent.memory.writes,
            "budget_used_steps": agent.budget.used_steps,
            "budget_used_tokens": agent.budget.used_tokens,
            "trajectory": state.trajectory,
            "evaluation_kind": "real_environment",
        }


def isolated_episode_pair(genome: AgentGenome, factory, n: int = 2) -> List[Dict[str, Any]]:
    """Run n episodes with fresh state; used by isolation tests."""
    runner = EpisodeRunner(genome, factory)
    return [runner.run(lambda: factory.reset()[0:2] if False else factory.env_reset(),
                       factory.env_step, episode_id=i) for i in range(n)]
