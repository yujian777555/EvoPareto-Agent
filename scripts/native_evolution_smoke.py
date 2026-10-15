"""Docker: native evolution smoke with FakeLLM (no API cost)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.evaluation.native_evolution_evaluator import (
    NativeEvolutionEvaluator,
    RandomSearchSampler,
)
from src.evolution.memory_evolution import MemoryEvolutionConfig, MemoryEvolutionLoop
from src.evolution.nsga3 import NSGA3


def make_native_env(split="valid_unseen", num_games=2, max_steps=8):
    from src.benchmark.native_alfworld import NativeALFWorldAdapter, NativeALFWorldConfig

    cfg = NativeALFWorldConfig(split=split, num_games=num_games, max_steps=max_steps)
    adapter = NativeALFWorldAdapter(cfg)
    adapter.reset()

    def reset_fn():
        return adapter._env.reset()

    def step_fn(actions):
        return adapter._env.step(list(actions))

    return reset_fn, step_fn, lambda: None


class FakeLLM:
    def __init__(self):
        self.n = 0

    def __call__(self, prompt):
        self.n += 1
        # pick first admissible-like line from prompt as action if present
        action = "look"
        for line in prompt.splitlines():
            if line.startswith("- "):
                action = line[2:].strip()
                break
        return action, {"calls": 1, "tokens_in": 20, "tokens_out": 5, "cost": 0.0}


def main():
    t0 = time.time()
    llm = FakeLLM()
    ev = NativeEvolutionEvaluator(make_native_env(), llm, n_tasks=2, max_steps=6)

    # 1) single genome
    g0 = AgentGenome("cot", "episodic", "self_critique", "balanced", 48)
    vec = ev.evaluate(g0)
    print("VEC", vec)

    # 2) evolution loop uses native evaluator
    cfg = MemoryEvolutionConfig(pop_size=3, n_offspring=3, seed=7,
                                use_adaptive=True, experience_mode="robust_peem")
    loop = MemoryEvolutionLoop(evaluator=ev.evaluate, config=cfg)
    loop.initialize()
    loop.run(1)
    print("EVO gens", loop.generation, "pop", len(loop.individuals),
          "hv", round(loop.current_hypervolume(), 4))

    # 3) random search independence
    rs = RandomSearchSampler(seed=3)
    rs_out = rs.run(ev.evaluate, 2)
    print("RS evals", len(rs_out), "archive", len(rs.archive))

    # 4) NSGA-III got native fitness
    assert all(ind.has_fitness() for ind in loop.individuals)

    payload = {
        "evaluation_kind": "real_environment",
        "fake_llm": True,
        "sample_vec": vec,
        "evo_generation": loop.generation,
        "evo_pop": len(loop.individuals),
        "evo_hv": loop.current_hypervolume(),
        "rs_evals": len(rs_out),
        "episodes": [e.to_dict() for e in ev.episodes[:4]],
        "wall_time": time.time() - t0,
    }
    out = "/results/native_alfworld/evolution_smoke/fake_llm_evolution.json"
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", out)
    print("SMOKE_OK")


if __name__ == "__main__":
    main()
