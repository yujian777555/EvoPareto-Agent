"""Replay a recorded native trajectory (Phase5-R3-R4-R2 Task B3)."""

from __future__ import annotations

import argparse
import json
import os
import sys

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", help="episode JSON with game_id + trajectory")
    ap.add_argument("--split", default="valid_train")
    args = ap.parse_args()
    rec = json.loads(open(args.trace, encoding="utf-8").read())
    # allow wrapper {"episodes":[...]}
    if "episodes" in rec and "game_id" not in rec:
        rec = rec["episodes"][0]
    game_id = rec.get("game_id") or ""
    traj = rec.get("trajectory") or []
    if not game_id or not traj:
        print("HISTORICAL_SUCCESS_UNREPLAYABLE: missing game_id/trajectory")
        return 2

    from src.benchmark.native_alfworld import NativeALFWorldEnv, NativeALFWorldConfig
    from src.benchmark.split_integrity import normalize_game_id

    cfg = NativeALFWorldConfig(split=args.split, num_games=1, max_steps=max(10, len(traj) + 2))
    env = NativeALFWorldEnv(cfg)
    # Force the exact game file
    obs, infos = env.reset(episode_index=0)
    if normalize_game_id(env.last_reset_meta.get("actual_game_id", "")) != normalize_game_id(game_id):
        # try to find index
        found = False
        for i in range(min(50, max(1, len(env._games)))):
            env.reset(episode_index=i)
            if normalize_game_id(env.last_reset_meta.get("actual_game_id", "")) == normalize_game_id(game_id):
                found = True
                break
        if not found:
            print("REPLAY_GAME_MISMATCH", env.last_reset_meta.get("actual_game_id"), game_id)
            return 3

    won = False
    final_step = -1
    for t, step in enumerate(traj):
        action = step.get("action")
        out = env.step([action])
        obs, scores, dones, ninfos = out[0], out[1], out[2], out[3]
        ninfos = ninfos if isinstance(ninfos, dict) else {}
        w = ninfos.get("won")
        won = bool(w[0] if isinstance(w, (list, tuple)) else w)
        final_step = t + 1
        if won:
            break

    result = {
        "replay_won": won,
        "replay_steps": final_step,
        "recorded_success": rec.get("success"),
        "recorded_steps": rec.get("steps"),
        "match_won": won == bool(rec.get("success")),
    }
    print(json.dumps(result))
    return 0 if result["match_won"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
