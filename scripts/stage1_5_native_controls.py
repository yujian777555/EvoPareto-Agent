"""Stage 1.5 native positive / negative controls.

Positive control = deterministic expert-INTENT policy (no LLM):
  official ALFRED high_pddl defines WHAT to do (goto/pickup/toggle/put);
  TextWorld grounding resolves it to admissible commands, searching
  receptacles when the object is not yet visible.

Negative control = legal non-completing actions (look-only).

Run inside Docker. 0 DeepSeek API calls.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

OUT = Path("/results/stage1_5")
OUT.mkdir(parents=True, exist_ok=True)

TASKS = [
    {
        "task_index": 0,
        "game_id": "/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990",
        "task_type": "look_at_obj_in_light",
    },
    {
        "task_index": 10,
        "game_id": "/data/json_2.1.1/valid_train/look_at_obj_in_light-Laptop-None-DeskLamp-309/trial_T20190907_185713_398582",
        "task_type": "look_at_obj_in_light",
    },
    {
        "task_index": 20,
        "game_id": "/data/json_2.1.1/valid_train/pick_and_place_simple-AlarmClock-None-Dresser-319/trial_T20190910_195319_108102",
        "task_type": "pick_and_place_simple",
    },
]


def norm(s: str) -> str:
    return s.lower().replace(" ", "")


class EnvView:
    def __init__(self, env):
        self.env = env
        obs, infos = env.reset(episode_index=0, force_game_file=env.config_path)
        self.obs = obs
        self.infos = infos if isinstance(infos, dict) else {}
        self.trajectory = []
        self.won = False
        self.done = False
        self.steps = 0
        self.actual_game_id = env.last_reset_meta.get("actual_game_id", "")

    def adm(self):
        a = self.infos.get("admissible_commands") or []
        if a and isinstance(a[0], (list, tuple)):
            a = list(a[0])
        return list(a)

    def obs_text(self):
        o = self.obs[0] if isinstance(self.obs, (list, tuple)) else self.obs
        return str(o)

    def step(self, cmd: str) -> bool:
        out = self.env.step([cmd])
        self.obs, scores, dones, ninfos = out[0], out[1], out[2], out[3]
        self.infos = ninfos if isinstance(ninfos, dict) else {}
        w = self.infos.get("won")
        self.won = bool(w[0] if isinstance(w, (list, tuple)) else w)
        d = dones[0] if isinstance(dones, (list, tuple)) else dones
        self.done = bool(d)
        self.steps += 1
        self.trajectory.append({
            "step": self.steps, "action": cmd, "won": self.won, "done": self.done,
            "obs": self.obs_text()[:300],
        })
        return self.won or self.done


def find_cmd(adm, pred):
    for a in adm:
        if pred(a.lower()):
            return a
    return None


def goto_receptacle(view, name: str):
    """go to <name> N. If already there (no go-to name), return False."""
    cmd = find_cmd(view.adm(), lambda l: l.startswith("go to " + norm(name)))
    if cmd:
        return not view.step(cmd)
    # already at location or location uses different wording
    return True


def search_until_visible(view, obj_name: str, prefer_prefix: str = "", max_visits: int = 24) -> bool:
    """Visit receptacles until `take <obj>` appears. Prefer expert-hinted type."""
    visited = set()
    for _ in range(max_visits):
        adm = view.adm()
        if find_cmd(adm, lambda l: l.startswith("take ") and norm(obj_name) in norm(l)):
            return True
        cands = [a for a in adm if a.lower().startswith("go to ") and a not in visited]
        if not cands:
            # try opening closed receptacles where we stand
            op = find_cmd(adm, lambda l: l.startswith("open "))
            if op and view.step(op):
                return False
            return find_cmd(view.adm(), lambda l: l.startswith("take ") and norm(obj_name) in norm(l))
        if prefer_prefix:
            preferred = [a for a in cands if a.lower().startswith("go to " + norm(prefer_prefix))]
            nxt = preferred[0] if preferred else cands[0]
        else:
            nxt = cands[0]
        visited.add(nxt)
        if view.step(nxt):
            return False
        # open closed things here
        adm = view.adm()
        op = find_cmd(adm, lambda l: l.startswith("open "))
        if op:
            if view.step(op):
                return False
    return find_cmd(view.adm(), lambda l: l.startswith("take ") and norm(obj_name) in norm(l))


def pickup(view, obj_name: str, prefer: str = "") -> bool:
    adm = view.adm()
    cmd = find_cmd(adm, lambda l: l.startswith("take ") and norm(obj_name) in norm(l))
    if cmd:
        return not view.step(cmd)
    if search_until_visible(view, obj_name, prefer_prefix=prefer):
        cmd = find_cmd(view.adm(), lambda l: l.startswith("take ") and norm(obj_name) in norm(l))
        if cmd:
            return not view.step(cmd)
    return True


def goto_anywhere_with(view, pred, max_visits: int = 20) -> str:
    """Navigate until admissible matches pred; return matching command or ''."""
    visited = set()
    for _ in range(max_visits):
        adm = view.adm()
        cmd = find_cmd(adm, pred)
        if cmd:
            return cmd
        cands = [a for a in adm if a.lower().startswith("go to ") and a not in visited]
        if not cands:
            return ""
        visited.add(cands[0])
        if view.step(cands[0]):
            return ""
    return find_cmd(view.adm(), pred)


def toggle(view, obj_name: str) -> bool:
    cmd = goto_anywhere_with(view, lambda l: l.startswith("use ") and norm(obj_name) in norm(l))
    if cmd:
        return not view.step(cmd)
    return True


def put_on(view, obj_name: str, target: str) -> bool:
    """TextWorld ALFWorld uses 'move X to Y' (not 'put')."""
    pred = (
        lambda l: (l.startswith("put ") or l.startswith("move "))
        and norm(obj_name) in norm(l)
        and (norm(target) in norm(l))
    )
    if not find_cmd(view.adm(), pred):
        goto_receptacle(view, target)
    adm = view.adm()
    cmd = find_cmd(adm, pred)
    if not cmd:
        cmd = find_cmd(
            adm,
            lambda l: (l.startswith("put ") or l.startswith("move "))
            and norm(obj_name) in norm(l),
        )
    if cmd:
        return not view.step(cmd)
    return True


def look_at(view, obj_name: str) -> bool:
    adm = view.adm()
    cmd = find_cmd(adm, lambda l: l.startswith("look at ") and norm(obj_name) in norm(l))
    if cmd:
        return not view.step(cmd)
    cmd = find_cmd(adm, lambda l: l.startswith("examine ") and norm(obj_name) in norm(l))
    if cmd:
        return not view.step(cmd)
    cmd = find_cmd(adm, lambda l: l == "look")
    if cmd:
        return not view.step(cmd)
    return True


def run_positive(task):
    gid = task["game_id"]
    d = json.load(open(os.path.join(gid, "traj_data.json")))
    plan = d["plan"]["high_pddl"]
    goal = ""
    turk = d.get("turk_annotations", {}).get("anns", [])
    if turk:
        goal = turk[0].get("task_desc", "")

    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv

    cfg = NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=24)
    env = NativeALFWorldEnv(cfg)
    env.config_path = gid + "/game.tw-pddl"
    view = EnvView(env)
    mapping_log = []

    for hs in plan:
        if view.won or view.done:
            break
        da = hs.get("discrete_action") or hs
        act = da.get("action")
        args = [str(x).lower() for x in (da.get("args") or [])]
        mapping_log.append({"high": {"action": act, "args": args}, "started_at_step": view.steps + 1})
        if act == "GotoLocation":
            loc = args[0] if args else ""
            if loc in ("desklamp", "lamp", "desk lamp"):
                cmd = goto_anywhere_with(view, lambda l: l.startswith("use ") and "lamp" in l)
                mapping_log[-1]["mapped"] = f"nav_to_use_{loc}"
            elif loc in ("book", "laptop", "alarmclock", "alarm clock"):
                prefer = {"book": "sidetable", "laptop": "bed", "alarmclock": "shelf",
                          "alarm clock": "shelf"}.get(loc, "")
                pickup(view, loc, prefer=prefer)  # will take if found
                mapping_log[-1]["mapped"] = f"find_{loc}"
            else:
                goto_receptacle(view, loc)
                mapping_log[-1]["mapped"] = f"go to {loc}*"
        elif act == "PickupObject":
            obj = args[0] if args else ""
            prefer = {"book": "sidetable", "laptop": "bed", "alarmclock": "shelf",
                      "alarm clock": "shelf"}.get(obj, "")
            pickup(view, obj, prefer=prefer)
            mapping_log[-1]["mapped"] = f"take {obj}*"
        elif act == "ToggleObject":
            obj = args[0] if args else ""
            toggle(view, obj)
            mapping_log[-1]["mapped"] = f"use {obj}*"
        elif act == "PutObject":
            obj = args[0] if args else ""
            tgt = args[1] if len(args) > 1 else ""
            put_on(view, obj, tgt)
            mapping_log[-1]["mapped"] = f"put {obj} on {tgt}*"
        elif act == "NoOp":
            obj = {0: "book", 10: "laptop", 20: "alarmclock"}.get(task["task_index"], "object")
            look_at(view, obj)
            mapping_log[-1]["mapped"] = f"look at {obj}*"

    # final fallback finishers
    if not view.won:
        look_at(view, "book" if task["task_index"] == 0 else "laptop")

    status = (
        "POSITIVE_CONTROL_PASS" if view.won
        else "POSITIVE_CONTROL_FAIL"
    )
    return {
        "task_index": task["task_index"],
        "game_id": gid,
        "actual_game_id": view.actual_game_id,
        "manifest_sha256": "27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7",
        "task_type": task["task_type"],
        "goal": goal,
        "expert_source": "official ALFRED traj_data.json high_pddl (converted to TextWorld via deterministic grounding search)",
        "expert_high_steps": plan,
        "admissible_mapping": mapping_log,
        "action_sequence": [t["action"] for t in view.trajectory],
        "observation_sequence": [t["obs"] for t in view.trajectory],
        "native_won": view.won,
        "native_done": view.done,
        "steps": view.steps,
        "status": status,
        "failure_reason": "" if view.won else "expert_intent_executed_without_native_won",
    }


def run_negative(task):
    gid = task["game_id"]
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv

    cfg = NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=8)
    env = NativeALFWorldEnv(cfg)
    env.config_path = gid + "/game.tw-pddl"
    view = EnvView(env)
    for _ in range(8):
        adm = view.adm()
        cmd = "look" if "look" in adm else (adm[0] if adm else "look")
        if view.step(cmd):
            break
    env.close()
    return {
        "task_index": task["task_index"],
        "game_id": gid,
        "action_sequence": [t["action"] for t in view.trajectory],
        "native_won": view.won,
        "steps": view.steps,
        "status": "NEGATIVE_CONTROL_PASS" if not view.won else "NEGATIVE_CONTROL_FAIL",
    }


def main():
    positives, negatives = [], []
    for task in TASKS:
        pos = run_positive(task)
        positives.append(pos)
        print("POS", task["task_index"], pos["status"], "won=", pos["native_won"],
              "steps=", pos["steps"])
        print("   actions:", pos["action_sequence"])
        neg = run_negative(task)
        negatives.append(neg)
        print("NEG", task["task_index"], neg["status"], "won=", neg["native_won"])

    (OUT / "positive_controls.json").write_text(
        json.dumps(positives, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "negative_controls.json").write_text(
        json.dumps(negatives, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    all_pos = all(p["status"] == "POSITIVE_CONTROL_PASS" for p in positives)
    all_neg = all(n["status"] == "NEGATIVE_CONTROL_PASS" for n in negatives)
    verdict = (
        "ENVIRONMENT_VALIDATED" if all_pos and all_neg
        else "ENVIRONMENT_UNVERIFIED" if not any(p["native_won"] for p in positives)
        else "ENVIRONMENT_OR_EVALUATOR_DEFECT"
    )
    validation = {
        "positive_all_pass": all_pos,
        "negative_all_pass": all_neg,
        "won_false_to_true_observed": any(p["native_won"] for p in positives),
        "won_stays_false_on_negative": all(not n["native_won"] for n in negatives),
        "per_task": {
            str(p["task_index"]): {
                "pos_status": p["status"], "pos_won": p["native_won"],
                "neg_status": negatives[i]["status"],
            }
            for i, p in enumerate(positives)
        },
        "environment_version": "alfworld TextWorld Docker alfworld-local:tw + volume alfworld-data",
        "verdict": verdict,
    }
    (OUT / "native_won_validation.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("VERDICT", verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
