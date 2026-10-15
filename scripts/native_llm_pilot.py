"""Stage E: tiny native ALFWorld + DeepSeek deepseek-flash pilot."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.backend.base import DeepSeekBackend
from src.benchmark.native_alfworld import NativeALFWorldAdapter, NativeALFWorldConfig
from src.runtime.interactive_agent import InteractiveAgent


def main() -> None:
    backend = DeepSeekBackend(max_retries=1, timeout=30)
    assert backend.has_credentials(), "DEEPSEEK_API_KEY missing"
    print("model", backend.model)

    def llm_generate(prompt: str) -> str:
        return backend.generate(prompt, budget=8).text

    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    agent = InteractiveAgent(genome, llm_generate, horizon=12)
    cfg = NativeALFWorldConfig(split="valid_unseen", num_games=2, max_steps=8)
    adapter = NativeALFWorldAdapter(cfg)

    episodes = []
    t0 = time.time()
    for i in range(2):
        out = adapter.run_episode_with_policy(agent.policy(), seed=i)
        out["model"] = backend.model
        out["api_usage"] = backend.usage()
        out["genome"] = genome.to_dict()
        episodes.append(out)
        print(json.dumps({
            "ep": i, "success": out["success"], "steps": out["steps"],
            "score": out["score"], "eval_kind": out["evaluation_kind"],
            "api_calls": backend.usage()["calls"],
        }, ensure_ascii=False))
    payload = {
        "benchmark": "alfworld_textworld",
        "evaluation_kind": "real_environment",
        "model": backend.model,
        "policy": "InteractiveAgent+DeepSeek",
        "episodes": episodes,
        "n_success": sum(1 for e in episodes if e["success"]),
        "api_usage": backend.usage(),
        "wall_time": time.time() - t0,
    }
    out_path = "/results/native_alfworld/pilot/deepseek_ep2.json"
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", out_path)
    print("STATUS", payload["n_success"], "/", len(episodes))


if __name__ == "__main__":
    main()
