"""D2: real DeepSeek H=30 on valid_train with full traces + global gate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.backend.base import DeepSeekBackend
from src.benchmark.native_alfworld import NativeALFWorldEnv, NativeALFWorldConfig
from src.runtime.api_budget import APICallGate
from src.runtime.episode_runner import EpisodeRunner


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()[:12]
    except Exception:
        return "unknown"


def main():
    backend = DeepSeekBackend(max_retries=1, timeout=30)
    gate = APICallGate(backend.generate, max_calls=80, max_cost_usd=1.0, max_retries=1)

    def llm(prompt: str):
        resp = gate.generate(prompt, budget=8)
        return {
            "text": resp.text,
            "usage": {
                "calls": 1,
                "tokens_in": resp.tokens_prompt,
                "tokens_out": resp.tokens_completion,
                "cost": resp.cost,
            },
            "model": resp.model,
        }

    genome = AgentGenome("plan_and_solve", "short_term", "self_critique", "balanced", 96)
    env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=2, max_steps=30))
    runner = EpisodeRunner(
        genome, llm, horizon=30, model="deepseek-flash",
        experiment_id="r4r2_d2_h30", git_sha=git_sha(),
    )

    episodes = []
    for i in range(2):
        print("EP", i, flush=True)
        out = runner.run(env.reset, env.step, episode_id=i, seed=11)
        episodes.append(out)
        print(json.dumps({
            "i": i, "success": out["success"], "steps": out["steps"],
            "game": out["game_id"][-45:], "tokens": (out["tokens_in"], out["tokens_out"]),
            "cost": out["cost_usd"], "term": out["termination_reason"],
        }), flush=True)

    snap = gate.snapshot()
    payload = {
        "model": "deepseek-flash",
        "split": "valid_train",
        "horizon": 30,
        "git_sha": git_sha(),
        "episodes": episodes,
        "api_snapshot": snap,
        "n_success": sum(1 for e in episodes if e["success"]),
        "note": "full trajectories included; historical H30 success not used",
    }
    outp = "/results/native_alfworld/r4r2_pilot/d2_h30_valid_train.json"
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", outp)
    print("SNAPSHOT", json.dumps(snap))

    # Save first episode for replay
    if episodes:
        with open("/results/native_alfworld/success_replay/episode0.json", "w", encoding="utf-8") as f:
            json.dump(episodes[0], f, indent=2)
    print("DONE success", payload["n_success"], "/ 2")


if __name__ == "__main__":
    main()
