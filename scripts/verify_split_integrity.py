"""Docker: verify split mapping + game IDs for valid_train/seen/unseen."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.benchmark.native_alfworld import NativeALFWorldEnv, NativeALFWorldConfig
from src.benchmark.split_integrity import SplitIntegrityError, resolve_split


def check_split(split: str, k: int = 2) -> dict:
    train_eval, rel = resolve_split(split)
    env = NativeALFWorldEnv(NativeALFWorldConfig(split=split, num_games=k, max_steps=3))
    rows = []
    for i in range(k):
        try:
            obs, infos = env.reset(episode_index=i)
            meta = getattr(env, "last_reset_meta", {})
            gid = meta.get("actual_game_id", "")
            ok = f"/json_2.1.1/{rel}/" in gid.replace("\\", "/")
            rows.append({
                "episode_index": i,
                "requested_split": split,
                "resolved_train_eval": train_eval,
                "dataset_path": meta.get("dataset_path"),
                "actual_game_id": gid,
                "in_requested_split": ok,
                "goal_preview": (str(obs[0])[:80] if obs else ""),
            })
        except SplitIntegrityError as e:
            rows.append({"episode_index": i, "error": f"SplitIntegrityError:{e}", "in_requested_split": False})
        except Exception as e:
            rows.append({"episode_index": i, "error": f"{type(e).__name__}:{e}", "in_requested_split": False})
    return {"split": split, "resolved_train_eval": train_eval, "rows": rows}


def main():
    out = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": []}
    for split in ("valid_train", "valid_seen", "valid_unseen"):
        print("CHECK", split, flush=True)
        out["results"].append(check_split(split, k=2))
    # fail closed probe
    try:
        resolve_split("not_a_split")
        out["fail_closed"] = False
    except SplitIntegrityError:
        out["fail_closed"] = True
    path = "/results/native_alfworld/split_integrity/split_check.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    for r in out["results"]:
        print(r["split"], r["resolved_train_eval"],
              [(x.get("in_requested_split"), (x.get("actual_game_id") or x.get("error", ""))[-50:]) for x in r["rows"]])
    print("FAIL_CLOSED", out["fail_closed"])
    print("WROTE", path)


if __name__ == "__main__":
    main()
