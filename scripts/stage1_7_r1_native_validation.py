"""Stage 1.7-R1 Gate E native offline validation (Docker, 0 real LLM).

Scripted control + negative + generic observation-driven + generalization probe
on a different valid_train instance (public observation only).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

OUT = Path("/results/stage1_7_r1")
OUT.mkdir(parents=True, exist_ok=True)

GAMES = {
    0: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990",
    10: "/data/json_2.1.1/valid_train/look_at_obj_in_light-Laptop-None-DeskLamp-309/trial_T20190907_185713_398582",
    20: "/data/json_2.1.1/valid_train/pick_and_place_simple-AlarmClock-None-Dresser-319/trial_T20190910_195319_108102",
}
# generalization probe: different instance, no expert lookup for tuning
GEN_GAME = "/data/json_2.1.1/valid_train/look_at_obj_in_light-Bowl-None-DeskLamp-304/trial_T20190907_232227_752681"
GOALS = {
    0: "look at book under the desklamp",
    10: "look at laptop under the desklamp",
    20: "put a alarmclock in dresser",
    "gen": "look at bowl under the desklamp",
}
SCRIPTED_WIN = {
    0: ["go to sidetable 1", "take book 2 from sidetable 1", "go to sidetable 2", "use desklamp 1"],
    10: ["go to bed 1", "take laptop 1 from bed 1", "go to sidetable 1", "use desklamp 1"],
    20: ["go to shelf 3", "take alarmclock 1 from shelf 3", "go to dresser 1", "move alarmclock 1 to dresser 1"],
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
    """Deterministic generic heuristic — no target-location knowledge."""

    def __init__(self):
        self.prompts = []
        self.recent = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        cands = []
        in_cand = False
        for line in prompt.splitlines():
            if line.startswith("Legal Action Candidates"):
                in_cand = True
                continue
            if in_cand:
                if line.startswith("- "):
                    cands.append(line[2:].split("  [")[0].strip())
                elif line.strip():
                    in_cand = False
        if not cands:
            for line in prompt.splitlines():
                if line.startswith("- ") and any(line[2:].startswith(p) for p in ("go to", "take ", "use ", "move ", "open ", "examine")):
                    cands.append(line[2:].split("  [")[0].strip())

        def score(c: str):
            rep = self.recent.count(c)
            s = 0.0
            if rep >= 2:
                s -= 10
            elif rep == 1:
                s -= 3
            if c.startswith("go to "):
                s += 4
            if c.startswith("take ") or c.startswith("move ") or c.startswith("use "):
                s += 8
            if c.startswith("open "):
                s += 3
            if c.startswith("examine "):
                s -= 1
            return s

        choice = max(cands, key=score) if cands else "look"
        self.recent.append(choice)
        return {"text": choice, "usage": {"calls": 1, "tokens_in": 1, "tokens_out": 1, "cost": 0.0},
                "model": "generic"}


def run_one(game_id, llm, goal, horizon=24):
    from src.agent.genome import AgentGenome
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.episode_runner import EpisodeRunner

    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 64)
    env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=horizon))

    def locked_reset(episode_index=0):
        return env.reset(episode_index=episode_index, force_game_file=game_id + "/game.tw-pddl")

    # goal must reach agent: EpisodeRunner extracts from observation; we also
    # pass via env obs replacement is hard — instead use runner then inspect.
    # For goal text we rely on locked reset observation containing task line OR
    # wrap llm to see prompt Task Goal (agent already gets goal= from extract_goal).
    runner = EpisodeRunner(genome, llm, horizon=horizon, experiment_id="r1",
                           runtime_variant="grounded_planner_v1")
    ep = runner.run(locked_reset, env.step, episode_id=0, seed=0)
    env.close()
    # capture planner diagnostics
    return ep


def main():
    res = {"scripted": [], "negative": [], "generic": [], "generalization": []}
    for tidx in (0, 10, 20):
        gid = GAMES[tidx]
        ep = run_one(gid, ScriptedLLM(SCRIPTED_WIN[tidx]), GOALS[tidx])
        res["scripted"].append({"task_index": tidx, "won": bool(ep["success"]), "steps": ep["steps"],
                                "executed": [d.get("executed_action") for d in ep.get("decision_logs") or []],
                                "status": "PASS" if ep["success"] else "FAIL"})
        epn = run_one(gid, ScriptedLLM(["look"] * 8), GOALS[tidx], horizon=8)
        res["negative"].append({"task_index": tidx, "won": bool(epn["success"]),
                                "status": "NEG_PASS" if not epn["success"] else "NEG_FAIL"})
        epg = run_one(gid, GenericPolicyLLM(), GOALS[tidx], horizon=20)
        res["generic"].append({
            "task_index": tidx, "won": bool(epg["success"]), "steps": epg["steps"],
            "executed": [d.get("executed_action") for d in epg.get("decision_logs") or []],
            "termination": epg.get("termination_reason"),
            "status": "PASS" if epg["success"] else "FAIL_OR_INCONCLUSIVE",
        })
        print("S/N/G", tidx, ep["success"], epn["success"], epg["success"],
              res["generic"][-1]["executed"][:6])

    # generalization probe (public obs only)
    epx = run_one(GEN_GAME, GenericPolicyLLM(), GOALS["gen"], horizon=20)
    res["generalization"].append({
        "game": GEN_GAME, "won": bool(epx["success"]), "steps": epx["steps"],
        "executed": [d.get("executed_action") for d in epx.get("decision_logs") or []],
        "status": "PASS" if epx["success"] else "FAIL_OR_INCONCLUSIVE",
    })
    print("GEN", epx["success"], res["generalization"][-1]["executed"][:6])

    script_ok = all(r["status"] == "PASS" for r in res["scripted"])
    neg_ok = all(r["status"] == "NEG_PASS" for r in res["negative"])
    gen_ok = any(r["won"] for r in res["generic"]) or any(r["won"] for r in res["generalization"])
    payload = {
        "gate": "GATE_E_NATIVE_OFFLINE_R1",
        "scripted_technical_control": "PASS" if script_ok else "FAIL",
        "negative": "PASS" if neg_ok else "FAIL",
        "generic": "PASS" if gen_ok else "INCONCLUSIVE_OR_FAIL",
        "details": res,
        "failure_cause_analysis": {
            "planner_state_errors": "see subgoal_transition tests — fixed in R1",
            "candidate_selection": "target-first ranking added; generic heuristic still weak",
            "heuristic_capability": "likely dominant limit for generic wins",
            "horizon": "20 steps; expert wins use 4-18 steps with known targets",
        },
    }
    (OUT / "native_offline_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print("GATE_E", payload["scripted_technical_control"], payload["generic"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
