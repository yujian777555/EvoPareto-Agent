"""Episode runner with full native traces (Phase5-R3-R4-R2 Task B)."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from src.agent.genome import AgentGenome
from src.runtime.behavioral_agent import BudgetMeter, MemoryStore
from src.runtime.interactive_agent import BudgetExhaustedStop, InteractiveAgent


LLMReturn = Union[str, Tuple[Any, ...], Dict[str, Any]]


def parse_llm_return(raw: Any) -> Tuple[str, Dict[str, Any]]:
    """Accept str | (text, usage) | {text, usage, model}."""
    if isinstance(raw, dict):
        text = str(raw.get("text", ""))
        usage = dict(raw.get("usage") or {})
        if "model" in raw:
            usage.setdefault("model", raw["model"])
        return text, usage
    if isinstance(raw, tuple) and len(raw) >= 2:
        return str(raw[0]), dict(raw[1] or {})
    return str(raw), {}


class EpisodeRunner:
    def __init__(
        self,
        genome: AgentGenome,
        llm_generate: Callable[[str], Any],
        *,
        horizon: int = 20,
        model: str = "deepseek-flash",
        experiment_id: str = "",
        git_sha: str = "",
    ) -> None:
        self.genome = genome
        self.llm_generate = llm_generate
        self.horizon = horizon
        self.model = model
        self.experiment_id = experiment_id
        self.git_sha = git_sha

    def make_agent(self) -> InteractiveAgent:
        return InteractiveAgent(self.genome, lambda p: parse_llm_return(self.llm_generate(p))[0], horizon=self.horizon)

    def extract_goal(self, observation: str, infos: Dict[str, Any]) -> str:
        for key in ("goal", "task_goal", "extra.goal"):
            if infos.get(key):
                v = infos[key]
                return str(v[0] if isinstance(v, (list, tuple)) else v)
        m = re.search(r"Your task is to:?\s*(.+)", observation or "")
        if m:
            return m.group(1).strip()
        for line in (observation or "").splitlines():
            if "task is to" in line.lower():
                return line.strip()
        return ""

    def run(self, env_reset, env_step, *, episode_id: int = 0, seed: int = 0) -> Dict[str, Any]:
        try:
            obs, infos = env_reset(episode_index=episode_id)
        except TypeError:
            obs, infos = env_reset()
        infos = infos if isinstance(infos, dict) else {}
        o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
        game_id = str(infos.get("actual_game_id") or "")
        if not game_id:
            gf = infos.get("extra.gamefile") or infos.get("gamefile")
            if gf:
                game_id = str(gf[0] if isinstance(gf, (list, tuple)) else gf)
        goal = self.extract_goal(str(o0), infos)
        agent = self.make_agent()

        state = {
            "api_calls": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_usd": 0.0,
            "estimated_tokens": 0,
            "llm_call_count": 0,
        }

        def usage_wrap(prompt: str) -> str:
            text, usage = parse_llm_return(self.llm_generate(prompt))
            state["llm_call_count"] += 1
            state["api_calls"] += int(usage.get("calls", 1))
            state["tokens_in"] += int(usage.get("tokens_in", 0))
            state["tokens_out"] += int(usage.get("tokens_out", 0))
            state["cost_usd"] += float(usage.get("cost", 0.0) or usage.get("cost_usd", 0.0))
            if usage.get("tokens_in") is None and usage.get("actual_in") is None:
                state["estimated_tokens"] += max(8, len(text) // 4)
            return text

        agent.llm_generate = usage_wrap

        success = False
        score = 0.0
        trajectory: List[Dict[str, Any]] = []
        termination_reason = "max_steps"
        last_obs = str(o0)
        for t in range(self.horizon):
            if not agent.budget.can_step():
                termination_reason = "budget_exhausted"
                break
            adm = list(infos.get("admissible_commands") or [])
            if adm and isinstance(adm[0], (list, tuple)):
                adm = list(adm[0])
            action = agent.select_action(str(o0), adm, goal=goal)
            out = env_step([action])
            obs, scores, dones, ninfos = out[0], out[1], out[2], out[3]
            o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
            score = scores[0] if isinstance(scores, (list, tuple)) else scores
            done = dones[0] if isinstance(dones, (list, tuple)) else dones
            ninfos = ninfos if isinstance(ninfos, dict) else {}
            won = False
            w = ninfos.get("won")
            if w is not None:
                won = bool(w[0] if isinstance(w, (list, tuple)) else w)
            adm_after = list(ninfos.get("admissible_commands") or [])
            if adm_after and isinstance(adm_after[0], (list, tuple)):
                adm_after = list(adm_after[0])
            trajectory.append({
                "step": t + 1,
                "observation_before": last_obs[:2000],
                "admissible_commands": adm[:80],
                "action": action,
                "observation_after": str(o0)[:2000],
                "score": float(score),
                "won": won,
                "done": bool(done),
                "llm_call_count": state["llm_call_count"],
            })
            last_obs = str(o0)
            infos = ninfos
            if won or done:
                success = won
                termination_reason = "won" if won else "env_done"
                break
        else:
            termination_reason = "max_steps"

        return {
            "experiment_id": self.experiment_id,
            "git_sha": self.git_sha,
            "benchmark": "alfworld_textworld",
            "evaluation_kind": "real_environment",
            "requested_split": infos.get("requested_split"),
            "actual_split": (game_id.split("/json_2.1.1/")[-1].split("/")[0] if "json_2.1.1" in game_id else None),
            "game_id": game_id,
            "task_type": (game_id.split("/")[-3] if game_id.count("/") >= 3 else ""),
            "model": self.model,
            "genome": self.genome.to_dict(),
            "seed": seed,
            "goal": goal,
            "success": bool(success),
            "termination_reason": termination_reason,
            "steps": len(trajectory),
            "api_calls": state["api_calls"],
            "tokens_in": state["tokens_in"],
            "tokens_out": state["tokens_out"],
            "cost_usd": state["cost_usd"],
            "estimated_tokens": state["estimated_tokens"],
            "llm_call_count": state["llm_call_count"],
            "reflection_count": agent.reflection_count,
            "trajectory": trajectory,
        }
