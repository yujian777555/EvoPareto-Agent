"""Docker: real ALFWorld offline smoke with frozen manifest (Mock LLM OK)."""

from __future__ import annotations

import json
import os
import sys
import time

os.environ.setdefault("ALFWORLD_DATA", "/data")
sys.path.insert(0, "/")

from src.agent.genome import AgentGenome
from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
from src.benchmark.split_integrity import SplitIntegrityError
from src.evaluation.objective_spec import SPEC_2
from src.runtime.episode_runner import EpisodeRunner


def mock_llm(prompt: str):
    action = "look"
    for line in prompt.splitlines():
        if line.startswith("- "):
            action = line[2:].strip()
            break
    return {"text": action, "usage": {"calls": 1, "tokens_in": 5, "tokens_out": 1, "cost": 0.0}, "model": "mock-llm"}


def main() -> int:
    out = {"checks": {}, "errors": []}
    # 1) import + data
    try:
        import alfworld  # noqa: F401

        out["checks"]["alfworld_importable"] = True
    except Exception as e:
        out["checks"]["alfworld_importable"] = False
        out["errors"].append(f"import:{e}")
        _write(out)
        return 2

    # 2) manifest
    mf_path = "/results/native_alfworld/development_task_pool.json"
    out["checks"]["manifest_exists"] = os.path.exists(mf_path)
    if out["checks"]["manifest_exists"]:
        import hashlib

        raw = open(mf_path, "rb").read()
        out["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
        mf = json.loads(raw)
        tasks = mf.get("tasks") or []
        out["checks"]["manifest_tasks"] = len(tasks)
        target = tasks[0]["game_id"] if tasks else ""
    else:
        target = ""

    # 3) native env reset/step
    try:
        env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=1, max_steps=8))
        obs, infos = env.reset(episode_index=0)
        meta = env.last_reset_meta
        out["checks"]["native_reset_pass"] = True
        out["actual_game_id"] = meta.get("actual_game_id")
        out["checks"]["requested_split"] = meta.get("requested_split")
        # manifest lock: if target known, must match
        if target:
            out["checks"]["manifest_game_match"] = out["actual_game_id"] == target or target in str(out["actual_game_id"]) or str(out["actual_game_id"]) in target
        o0 = obs[0] if isinstance(obs, (list, tuple)) else obs
        step_out = env.step(["look"])
        out["checks"]["native_step_pass"] = True
        ninfos = step_out[3] if len(step_out) > 3 else {}
        w = ninfos.get("won") if isinstance(ninfos, dict) else None
        out["native_won"] = bool(w[0] if isinstance(w, (list, tuple)) else w)
    except Exception as e:
        out["checks"]["native_reset_pass"] = False
        out["checks"]["native_step_pass"] = False
        out["errors"].append(f"native:{type(e).__name__}:{e}")
        _write(out)
        return 3

    # 4) EpisodeRunner + 2D fitness
    try:
        genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
        runner = EpisodeRunner(genome, mock_llm, horizon=5, model="mock-llm",
                               experiment_id="native_smoke", git_sha=os.environ.get("GIT_SHA", "docker"))
        ep = runner.run(env.reset, env.step, episode_id=0, seed=11)
        out["checks"]["episode_runner_pass"] = True
        out["episode"] = {
            k: ep.get(k) for k in (
                "success", "steps", "termination_reason", "game_id", "goal",
                "tokens_in", "tokens_out", "cost_usd", "git_sha", "evaluation_kind",
            )
        }
        fit = [1.0 if ep["success"] else 0.0, ep["cost_usd"]]
        SPEC_2.validate_vector(fit)
        out["checks"]["fitness_2d_pass"] = True
        out["fitness"] = fit
    except Exception as e:
        out["checks"]["episode_runner_pass"] = False
        out["errors"].append(f"episode:{e}")

    out["checks"]["result_writable"] = True
    out["native_dry_run_status"] = (
        "PASS"
        if all(out["checks"].get(k) for k in (
            "alfworld_importable", "native_reset_pass", "native_step_pass",
            "episode_runner_pass", "fitness_2d_pass",
        ))
        else "FAIL"
    )
    _write(out)
    print(json.dumps(out, indent=2)[:1500])
    return 0 if out["native_dry_run_status"] == "PASS" else 4


def _write(out):
    p = "/results/pilot1_final_offline/native_smoke.json"
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("WROTE", p)


if __name__ == "__main__":
    raise SystemExit(main())
