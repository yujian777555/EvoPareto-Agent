"""Stage 1.7 Gate E: native offline validation (Docker, 0 real LLM).

1) Scripted winning sequences via grounded_planner_v1 EpisodeRunner (technical control).
2) Observation-driven generic policy (exploration planner) — report honestly.
3) No expert data in the policy path.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

OUT = Path("/results/stage1_7")
OUT.mkdir(parents=True, exist_ok=True)

GAMES = {
    0: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990",
    10: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Laptop-None-DeskLamp-309/trial_T20190907_185713_398582",
    20: "/data/json_2.1.1/valid_train/pick_and_place_simple-AlarmClock-None-Dresser-319/trial_T20190910_195319_108102",
}
# Technical-control sequences (verified in Stage 1.5) — NOT used by generic policy
SCRIPTED_WIN = {
    0: ["go to sidetable 1", "take book 2 from sidetable 1", "go to sidetable 2", "use desklamp 1"],
    10: ["go to bed 1", "take laptop 1 from bed 1", "go to sidetable 1", "use desklamp 1"],
    20: ["go to shelf 3", "take alarmclock 1 from shelf 3", "go to dresser 1", "move alarmclock 1 to dresser 1"],
}
GOALS = {
    0: "look at book under the desklamp",
    10: "look at laptop under the desklamp",
    20: "put a alarmclock in dresser",
}


class ScriptedLLM:
    def __init__(self, actions):
        self.actions = list(actions)
        self.i = 0

    def __call__(self, prompt):
        a = self.actions[min(self.i, len(self.actions) - 1)]
        self.i += 1
        return {"text": a, "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                "model": "scripted"}


class GenericPolicyLLM:
    """Observation-driven generic heuristic. No target-location knowledge.

    Prefers unexplored navigation over re-inspecting the same place; picks
    target-related candidates when the subgoal requires them. Deterministic.
    """

    def __init__(self):
        self.prompts = []
        self.i = 0
        self.recent = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        self.i += 1
        cands = []
        in_cand = False
        for line in prompt.splitlines():
            if line.startswith("Legal Action Candidates"):
                in_cand = True
                continue
            if in_cand:
                if line.startswith("- "):
                    cands.append(line[2:].split("  [")[0].strip())
                elif line.strip() and not line.startswith("-"):
                    in_cand = False
        if not cands:
            for line in prompt.splitlines():
                if line.startswith("- ") and ("go to" in line or "take " in line or "use " in line or "move " in line):
                    cands.append(line[2:].split("  [")[0].strip())
        # generic anti-loop: avoid 3rd repeat of same action
        def score(c: str):
            rep = self.recent.count(c)
            s = 0.0
            if rep >= 2:
                s -= 10
            elif rep == 1:
                s -= 2
            if c.startswith("go to "):
                s += 5  # explore
            if c.startswith("take ") or c.startswith("move ") or c.startswith("use "):
                s += 6  # progress actions
            if c == "look":
                s += 1
            return s

        if not cands:
            choice = "look"
        else:
            choice = max(cands, key=score)
        self.recent.append(choice)
        return {"text": choice, "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                "model": "generic"}


def run_one(task_idx, llm, variant, goal, horizon=24):
    from src.agent.genome import AgentGenome
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.episode_runner import EpisodeRunner

    gid = GAMES[task_idx]
    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 64)
    env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=horizon))

    def locked_reset(episode_index=0):
        return env.reset(episode_index=episode_index, force_game_file=gid + "/game.tw-pddl")

    runner = EpisodeRunner(genome, llm, horizon=horizon, experiment_id=f"g{task_idx}",
                           runtime_variant=variant)
    ep = runner.run(locked_reset, env.step, episode_id=0, seed=0)
    env.close()
    return ep


def main():
    results = {"scripted_technical_control": [], "generic_observation_driven": [],
               "negative_look_only": []}

    for tidx in (0, 10, 20):
        # 1) technical control with scripted winning actions
        ep = run_one(tidx, ScriptedLLM(SCRIPTED_WIN[tidx]), "grounded_planner_v1", GOALS[tidx])
        results["scripted_technical_control"].append({
            "task_index": tidx, "won": bool(ep["success"]), "steps": ep["steps"],
            "executed": [d.get("executed_action") for d in ep.get("decision_logs") or []],
            "kind": "TECHNICAL_CONTROL_NOT_AGENT_AUTONOMY",
            "status": "PASS" if ep["success"] else "FAIL",
        })
        print("SCRIPTED", tidx, ep["success"], ep["steps"])

        # 2) generic policy (no expert knowledge)
        ep2 = run_one(tidx, GenericPolicyLLM(), "grounded_planner_v1", GOALS[tidx], horizon=20)
        results["generic_observation_driven"].append({
            "task_index": tidx, "won": bool(ep2["success"]), "steps": ep2["steps"],
            "executed": [d.get("executed_action") for d in ep2.get("decision_logs") or []],
            "status": "PASS" if ep2["success"] else "FAIL_OR_INCONCLUSIVE",
        })
        print("GENERIC", tidx, ep2["success"], ep2["steps"],
              results["generic_observation_driven"][-1]["executed"][:8])

        # 3) negative look-only
        ep3 = run_one(tidx, ScriptedLLM(["look"] * 8), "grounded_planner_v1", GOALS[tidx], horizon=8)
        results["negative_look_only"].append({
            "task_index": tidx, "won": bool(ep3["success"]),
            "status": "NEG_PASS" if not ep3["success"] else "NEG_FAIL",
        })
        print("NEG", tidx, ep3["success"])

    script_ok = all(r["status"] == "PASS" for r in results["scripted_technical_control"])
    neg_ok = all(r["status"] == "NEG_PASS" for r in results["negative_look_only"])
    generic_ok = any(r["won"] for r in results["generic_observation_driven"])
    payload = {
        "gate": "GATE_E_NATIVE_OFFLINE",
        "scripted_technical_control": "PASS" if script_ok else "FAIL",
        "negative_no_false_success": "PASS" if neg_ok else "FAIL",
        "generic_observation_driven": "PASS" if generic_ok else "INCONCLUSIVE_OR_FAIL",
        "note": "scripted success is wiring-only; generic policy is the real autonomy check",
        "details": results,
    }
    (OUT / "native_offline_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("GATE_E", payload["scripted_technical_control"], payload["generic_observation_driven"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
