"""Gate C: native success propagation through EpisodeRunner (offline, Docker)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

OUT = Path("/results/stage1_5")
OUT.mkdir(parents=True, exist_ok=True)

# Legal winning sequences verified in Stage 1.5 (not fed to real A/B agent)
SEQUENCES = {
    0: [
        "go to sidetable 1",
        "take book 2 from sidetable 1",
        "go to sidetable 2",
        "use desklamp 1",
    ],
    10: [
        "go to bed 1",
        "take laptop 1 from bed 1",
        "go to sidetable 1",
        "use desklamp 1",
    ],
    20: [
        "go to shelf 3",
        "take alarmclock 1 from shelf 3",
        "go to dresser 1",
        "move alarmclock 1 to dresser 1",
    ],
}
GAMES = {
    0: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990",
    10: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Laptop-None-DeskLamp-309/trial_T20190907_185713_398582",
    20: "/data/json_2.1.1/valid_train/pick_and_place_simple-AlarmClock-None-Dresser-319/trial_T20190910_195319_108102",
}


class ScriptedPolicy:
    def __init__(self, actions):
        self.actions = list(actions)
        self.i = 0

    def __call__(self, prompt):
        # EpisodeRunner llm_generate — returns next scripted action as text
        a = self.actions[min(self.i, len(self.actions) - 1)]
        self.i += 1
        return {
            "text": a,
            "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
            "model": "scripted",
        }


def main():
    from src.agent.genome import AgentGenome
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.episode_runner import EpisodeRunner

    results = []
    for tidx, actions in SEQUENCES.items():
        gid = GAMES[tidx]
        genome = AgentGenome("cot", "short_term", "none", "balanced", 64)
        policy = ScriptedPolicy(actions)

        def mk_env():
            env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=16))
            return env

        env = mk_env()

        def locked_reset(episode_index=0):
            obs, infos = env.reset(episode_index=episode_index, force_game_file=gid + "/game.tw-pddl")
            return obs, infos

        runner = EpisodeRunner(genome, policy, horizon=16, experiment_id=f"gatec{tidx}",
                               runtime_variant="shared_repaired")
        ep = runner.run(locked_reset, env.step, episode_id=0, seed=0)
        ok = bool(ep["success"])
        results.append({
            "task_index": tidx,
            "game_id": gid,
            "action_sequence": actions,
            "executed": [d.get("executed_action") for d in ep.get("decision_logs") or []],
            "native_won": ok,
            "episode_success": ep["success"],
            "steps": ep["steps"],
            "termination_reason": ep["termination_reason"],
            "status": "GATE_C_PASS" if ok else "GATE_C_FAIL",
        })
        print("GATE_C", tidx, "won=", ok, "steps=", ep["steps"], "executed=", results[-1]["executed"])
        env.close()

        # negative: look-only must NOT succeed
        env2 = mk_env()
        neg_policy = ScriptedPolicy(["look"] * 6)

        def neg_reset(episode_index=0):
            return env2.reset(episode_index=episode_index, force_game_file=gid + "/game.tw-pddl")

        epn = EpisodeRunner(genome, neg_policy, horizon=8, experiment_id=f"neg{tidx}").run(
            neg_reset, env2.step, episode_id=0, seed=0
        )
        results[-1]["negative_success"] = epn["success"]
        results[-1]["negative_status"] = "NEG_PASS" if not epn["success"] else "NEG_FAIL"
        print("  neg", results[-1]["negative_status"])
        env2.close()

    all_pass = all(r["status"] == "GATE_C_PASS" and r["negative_status"] == "NEG_PASS" for r in results)
    payload = {
        "gate": "GATE_C_NATIVE_SUCCESS_PROPAGATION",
        "result": "PASS" if all_pass else "FAIL",
        "per_task": results,
        "expert_sequences_used_as": "offline_test_policy_only_not_injected_into_real_AB_agent",
    }
    (OUT / "gate_c_native_propagation.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("GATE_C", payload["result"])
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
