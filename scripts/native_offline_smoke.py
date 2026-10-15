"""Docker: native ALFWorld smoke with mandatory manifest lock (Pilot1 microfix)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.benchmark.manifest_lock import (
    canonical_game_id,
    load_manifest,
    manifest_sha256,
    select_task,
    verify_actual_matches_target,
)
from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
from src.evaluation.objective_spec import SPEC_2
from src.runtime.episode_runner import EpisodeRunner


def mock_llm(prompt: str):
    action = "look"
    for line in prompt.splitlines():
        if line.startswith("- "):
            action = line[2:].strip()
            break
    return {"text": action, "usage": {"calls": 1, "tokens_in": 5, "tokens_out": 1, "cost": 0.0}, "model": "mock-llm"}


REQUIRED = [
    "alfworld_importable",
    "manifest_exists",
    "manifest_valid",
    "manifest_game_match",
    "native_reset_pass",
    "native_step_pass",
    "episode_runner_pass",
    "fitness_2d_pass",
    "result_writable",
]


def main() -> int:
    out: dict = {"checks": {k: False for k in REQUIRED}, "errors": []}
    try:
        import alfworld  # noqa: F401

        out["checks"]["alfworld_importable"] = True
    except Exception as e:
        out["errors"].append(f"import:{e}")
        return _finish(out)

    mf_path = "/results/native_alfworld/development_task_pool.json"
    out["checks"]["manifest_exists"] = os.path.exists(mf_path)
    if not out["checks"]["manifest_exists"]:
        out["errors"].append("manifest missing")
        return _finish(out)
    try:
        mf = load_manifest(mf_path)
        out["manifest_sha256"] = manifest_sha256(mf_path)
        out["checks"]["manifest_valid"] = True
    except Exception as e:
        out["errors"].append(f"manifest:{e}")
        return _finish(out)

    task = select_task(mf, int(os.environ.get("TASK_INDEX", "0")))
    out["selected_manifest_game_id"] = task.get("game_id")
    out["selected_task_fingerprint"] = task.get("fingerprint")

    try:
        env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=8))
        target_can = canonical_game_id(task["game_id"])
        # Manifest first: force exact game file, then verify identity.
        game_file = str(task["game_id"])
        if not game_file.endswith("game.tw-pddl"):
            game_file = game_file.rstrip("/") + "/game.tw-pddl"
        obs, infos = env.reset(episode_index=0, force_game_file=game_file)
        actual_id = env.last_reset_meta.get("actual_game_id", "")
        can_a, can_t = verify_actual_matches_target(actual_id, task["game_id"])
        out["checks"]["manifest_game_match"] = True
        out["actual_game_id"] = actual_id
        out["canonical_game_id"] = can_a
        out["checks"]["native_reset_pass"] = True
    except Exception as e:
        out["errors"].append(f"native_reset:{type(e).__name__}:{e}")
        return _finish(out)

    try:
        step_out = env.step(["look"])
        out["checks"]["native_step_pass"] = True
        ninfos = step_out[3] if len(step_out) > 3 else {}
        w = ninfos.get("won") if isinstance(ninfos, dict) else None
        out["native_won"] = bool(w[0] if isinstance(w, (list, tuple)) else w)
    except Exception as e:
        out["errors"].append(f"native_step:{e}")
        return _finish(out)

    try:
        genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
        runner = EpisodeRunner(genome, mock_llm, horizon=5, model="mock-llm",
                               experiment_id="native_smoke_manifest",
                               git_sha=os.environ.get("GIT_SHA", "docker"))
        env2 = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=8))
        ep = runner.run(
            lambda episode_index=0: env2.reset(episode_index=episode_index, force_game_file=game_file),
            env2.step,
            episode_id=0,
            seed=11,
        )
        out["checks"]["episode_runner_pass"] = True
        out["genome"] = genome.to_dict()
        out["episode"] = {
            k: ep.get(k) for k in (
                "success", "steps", "termination_reason", "game_id", "goal",
                "tokens_in", "tokens_out", "cost_usd", "git_sha", "evaluation_kind",
            )
        }
        fit = [1.0 if ep["success"] else 0.0, float(ep["cost_usd"])]
        SPEC_2.validate_vector(fit)
        out["checks"]["fitness_2d_pass"] = True
        out["fitness"] = fit
        out["trajectory_len"] = len(ep.get("trajectory") or [])
    except Exception as e:
        out["errors"].append(f"episode:{e}")

    return _finish(out)


def _finish(out: dict) -> int:
    out["checks"]["result_writable"] = True
    ok = all(out["checks"].get(k) for k in REQUIRED)
    out["native_dry_run_status"] = "PASS" if ok else "FAIL"
    p = "/results/pilot1_final_admission_verified/native_smoke.json"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    # also task_identity
    ident = {
        "manifest_sha256": out.get("manifest_sha256"),
        "selected_manifest_game_id": out.get("selected_manifest_game_id"),
        "actual_game_id": out.get("actual_game_id"),
        "canonical_game_id": out.get("canonical_game_id"),
        "git_sha": out.get("episode", {}).get("git_sha"),
        "split": "valid_train",
    }
    with open("/results/pilot1_final_admission_verified/task_identity.json", "w", encoding="utf-8") as f:
        json.dump(ident, f, indent=2)
    print(json.dumps(out, indent=2)[:1800])
    return 0 if ok else 4


if __name__ == "__main__":
    raise SystemExit(main())
