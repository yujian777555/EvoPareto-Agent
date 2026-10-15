"""Docker-based native ALFWorld pilot (Stage C/E).

Runs inside `alfworld-local:tw` image with volume `alfworld-data`.
Uses a rule/random policy first (env connectivity), then optional LLM policy.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")


def rule_policy(obs, admissible):
    """Deterministic heuristic for connectivity (not gold trajectory)."""
    o = (obs or "").lower()
    for a in admissible:
        al = a.lower()
        if al.startswith("go to") and any(k in o for k in ("you are in", "looking quickly")):
            return a
        if al.startswith("take ") and ("you see" in o or "on the" in o):
            return a
        if al.startswith("open ") and "closed" in o:
            return a
        if al.startswith("examine "):
            return a
    return admissible[0] if admissible else "look"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=15)
    ap.add_argument("--split", default="valid_unseen")
    ap.add_argument("--out", default="/data/pilot_results.json")
    args = ap.parse_args()

    sys.path.insert(0, "/src")
    # Local package may be mounted at /src; else inline import path
    try:
        from src.benchmark.native_alfworld import NativeALFWorldAdapter, NativeALFWorldConfig
    except Exception:
        # running inside container without src mount
        import importlib.util

        print("WARN: src package not on path; using inline adapter logic")
        raise

    cfg = NativeALFWorldConfig(split=args.split, num_games=args.episodes, max_steps=args.max_steps)
    adapter = NativeALFWorldAdapter(cfg)
    results = []
    t0 = time.time()
    for i in range(args.episodes):
        out = adapter.run_episode_with_policy(rule_policy, seed=i)
        results.append(out)
        print(json.dumps({
            "ep": i, "success": out["success"], "steps": out["steps"],
            "score": out["score"], "eval_kind": out["evaluation_kind"],
        }))
    payload = {
        "benchmark": "alfworld_textworld",
        "evaluation_kind": "real_environment",
        "split": args.split,
        "policy": "rule_policy",
        "episodes": results,
        "n_episodes": len(results),
        "n_success": sum(1 for r in results if r["success"]),
        "wall_time": time.time() - t0,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("WROTE", args.out)


if __name__ == "__main__":
    main()
