"""Docker: horizon sensitivity diagnosis on development pool (FakeLLM or DeepSeek)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.evaluation.native_evolution_evaluator import NativeEvolutionEvaluator
from src.evaluation.progress_signals import classify_failure, progress_signals
from src.runtime.api_budget import APICallGate
from src.runtime.episode_runner import EpisodeRunner


def make_env(episode_pool_size=3):
    from src.benchmark.native_alfworld import NativeALFWorldEnv, NativeALFWorldConfig

    cfg = NativeALFWorldConfig(split="valid_train", num_games=episode_pool_size, max_steps=30)
    env = NativeALFWorldEnv(cfg)

    def reset_fn(episode_index=0):
        return env.reset(episode_index=episode_index)

    def step_fn(actions):
        return env.step(list(actions))

    return reset_fn, step_fn


class FakeLLM:
    def __call__(self, prompt):
        action = "look"
        for line in prompt.splitlines():
            if line.startswith("- "):
                action = line[2:].strip()
                break
        return action


def run_horizon(h: int, llm_factory, n_eps: int = 2, budget_calls: int = 200):
    reset_fn, step_fn = make_env(max(2, n_eps))
    if llm_factory is None:
        gen = FakeLLM()
        def wrapped(p):
            return gen(p)
    else:
        gate = APICallGate(llm_factory, max_calls=budget_calls, max_cost_usd=0.5, max_retries=1)
        def wrapped(p):
            return gate.generate(p, budget=8).text
    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 64)
    runner = EpisodeRunner(genome, wrapped, horizon=h)
    rows = []
    for i in range(n_eps):
        try:
            out = runner.run(reset_fn, step_fn, episode_id=i, seed=i)
        except Exception as e:
            import traceback

            out = {
                "success": False, "steps": 0,
                "termination_reason": f"environment_error:{type(e).__name__}:{e}",
                "goal": "", "game_id": "", "trajectory": [], "api_calls": 0,
                "traceback": traceback.format_exc()[-500:],
            }
        prog = progress_signals(out.get("trajectory", []), out.get("goal", ""))
        rows.append({
            "horizon": h,
            "episode_id": i,
            "game_id": out.get("game_id", ""),
            "goal": out.get("goal", ""),
            "success": out.get("success", False),
            "steps": out.get("steps", 0),
            "termination_reason": out.get("termination_reason", ""),
            "failure_class": classify_failure(out.get("termination_reason", ""), out.get("success", False)),
            "api_calls": out.get("api_calls", 0),
            "tokens_in": out.get("tokens_in", 0),
            "tokens_out": out.get("tokens_out", 0),
            "cost_usd": out.get("cost_usd", 0.0),
            "progress": prog,
        })
    summary = {
        "horizon": h,
        "episodes": len(rows),
        "success": sum(1 for r in rows if r["success"]),
        "avg_steps": sum(r["steps"] for r in rows) / max(1, len(rows)),
        "budget_exhausted": sum(1 for r in rows if r["failure_class"] == "budget_exhausted"),
        "max_steps": sum(1 for r in rows if r["failure_class"] == "max_steps"),
        "stalled": sum(1 for r in rows if r["failure_class"] == "stalled_no_obs_change"),
        "progress_state_changes": sum(r["progress"]["state_changes"] for r in rows),
        "repeated_actions": sum(r["progress"]["repeated_actions"] for r in rows),
    }
    return summary, rows


def main():
    mode = os.environ.get("DS_MODE", "fake")  # fake | deepseek
    out_dir = "/results/native_alfworld/horizon_diagnosis"
    os.makedirs(out_dir, exist_ok=True)
    all_rows = []
    summaries = []
    api_total = 0
    for h in (10, 20, 30):
        print("HORIZON", h, "mode", mode, flush=True)
        if mode == "deepseek":
            from src.backend.base import DeepSeekBackend

            backend = DeepSeekBackend(max_retries=1, timeout=25)
            summary, rows = run_horizon(h, backend.generate, n_eps=2, budget_calls=100)
            api_total += sum(r.get("api_calls", 0) for r in rows)
        else:
            summary, rows = run_horizon(h, None, n_eps=2, budget_calls=10)
        summaries.append(summary)
        all_rows.extend(rows)
        print(json.dumps(summary), flush=True)
        # Hard stop if real API budget near cap
        if mode == "deepseek" and api_total > 80:
            print("API soft stop", api_total)
            break

    payload = {
        "mode": mode,
        "code_note": "diagnostic only; valid_train split",
        "horizons": summaries,
        "episodes": all_rows,
        "api_calls_total": api_total,
    }
    with open(f"{out_dir}/horizon_{mode}.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", out_dir)


if __name__ == "__main__":
    main()
