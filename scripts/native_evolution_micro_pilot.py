"""Docker: micro native evolution pilot with real DeepSeek (hard cap 100 API calls)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.backend.base import DeepSeekBackend
from src.evaluation.native_evolution_evaluator import NativeEvolutionEvaluator, RandomSearchSampler
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop

HARD_CAP_CALLS = 100
HARD_CAP_COST = 1.0


def make_native_env(split="valid_unseen", num_games=2, max_steps=6):
    from src.benchmark.native_alfworld import NativeALFWorldAdapter, NativeALFWorldConfig

    cfg = NativeALFWorldConfig(split=split, num_games=num_games, max_steps=max_steps)
    adapter = NativeALFWorldAdapter(cfg)

    def reset_fn(episode_index=0):
        # Rotate through distinct native game instances.
        if adapter._env is None:
            adapter.reset()
        return adapter._env.reset(episode_index=episode_index)

    def step_fn(actions):
        return adapter._env.step(list(actions))

    return reset_fn, step_fn, lambda: None


def main():
    backend = DeepSeekBackend(max_retries=1, timeout=25)
    assert backend.has_credentials()
    usage0 = backend.usage()

    def llm_generate(prompt: str):
        u_before = backend.usage()
        text = backend.generate(prompt, budget=8).text
        u = backend.usage()
        return text, {
            "calls": u["calls"] - u_before["calls"] or 1,
            "tokens_in": u["prompt_tokens"] - u_before["prompt_tokens"],
            "tokens_out": u["completion_tokens"] - u_before["completion_tokens"],
            "cost": u["cost"] - u_before["cost"],
        }

    ev = NativeEvolutionEvaluator(make_native_env(), llm_generate, n_tasks=2, max_steps=5)

    # Mini evolution: pop=3, gens=1 => 3 init + 3 offspring = 6 genomes * 2 tasks
    cfg = MemoryEvolutionConfig(pop_size=3, n_offspring=3, seed=11,
                                use_adaptive=True, experience_mode="robust_peem")
    loop = MemoryEvolutionLoop(evaluator=ev.evaluate, config=cfg)
    loop.initialize()
    loop.run(1)

    # Tiny RS arm: 2 more genomes
    rs = RandomSearchSampler(seed=5)
    rs.run(ev.evaluate, 2)

    usage = backend.usage()
    calls = usage["calls"] - usage0["calls"]
    cost = usage["cost"] - usage0["cost"]
    assert calls <= HARD_CAP_CALLS, f"API cap exceeded {calls}"
    assert cost <= HARD_CAP_COST, f"cost cap exceeded {cost}"

    payload = {
        "model": backend.model,
        "evaluation_kind": "real_environment",
        "api_calls": calls,
        "tokens_in": usage["prompt_tokens"] - usage0["prompt_tokens"],
        "tokens_out": usage["completion_tokens"] - usage0["completion_tokens"],
        "cost_usd": cost,
        "hard_cap_calls": HARD_CAP_CALLS,
        "hard_cap_cost": HARD_CAP_COST,
        "evo_generation": loop.generation,
        "evo_hv": loop.current_hypervolume(),
        "evo_front": len(loop.pareto_front()),
        "n_episodes": len(ev.episodes),
        "n_success": sum(1 for e in ev.episodes if e.success),
        "episodes": [e.to_dict() for e in ev.episodes],
        "termination_reasons": [e.termination_reason for e in ev.episodes],
    }
    out = "/results/native_alfworld/micro_pilot/deepseek_micro_evolution.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", out)
    print("MICRO", json.dumps({k: payload[k] for k in
          ("api_calls", "tokens_in", "tokens_out", "cost_usd", "n_success", "n_episodes", "evo_generation")}))
    print("REASONS", payload["termination_reasons"])


if __name__ == "__main__":
    main()
