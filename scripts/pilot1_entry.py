"""Pilot 1 entry: DeepSeek + ALFWorld wiring with dry-run (0 live API this phase)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def build_config(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "model": "deepseek-flash",
        "environment": "ALFWorld TextWorld",
        "split": args.split,
        "horizon": args.horizon,
        "objective_version": "candidate_2obj",
        "maximize": [True, False],
        "max_physical_http": args.physical_cap,
        "max_estimated_cost_usd": args.cost_cap,
        "mode": args.mode,
        "experiment_id": args.experiment_id,
        "ledger_path": args.ledger_path,
        "task_manifest": args.task_manifest,
        "task_index": int(getattr(args, "task_index", 0)),
        "output_dir": args.output_dir,
        "seed": args.seed,
    }


def dry_run(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = build_config(args)
    out: Dict[str, Any] = {"config": cfg, "checks": {}}
    # 1) config validation
    out["checks"]["config_ok"] = cfg["max_physical_http"] > 0 and cfg["max_estimated_cost_usd"] > 0
    out["checks"]["objective_ok"] = cfg["objective_version"] == "candidate_2obj" and cfg["maximize"] == [True, False]
    # 2) output dir
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    out["checks"]["output_writable"] = outdir.is_dir()
    # 3) task manifest
    mf = Path(args.task_manifest)
    out["checks"]["manifest_exists"] = mf.exists()
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            out["checks"]["manifest_valid"] = bool(data)
        except Exception:
            out["checks"]["manifest_valid"] = False
    # 4) ALFWorld availability (native)
    try:
        import alfworld  # noqa: F401

        out["checks"]["alfworld_importable"] = True
    except Exception:
        out["checks"]["alfworld_importable"] = False
    # 5) genome → evaluator wiring (mock)
    from src.agent.genome import AgentGenome
    from src.evaluation.objective_spec import SPEC_2

    g = AgentGenome("cot", "short_term", "self_critique", "balanced", 48)
    fake_fit = [0.5, 0.01]
    SPEC_2.validate_vector(fake_fit)
    out["checks"]["fitness_2d_ok"] = True
    # 6) strict gate required in live mode
    from src.runtime.http_budget import get_global_gate

    out["checks"]["gate_required_in_live"] = True
    out["checks"]["gate_installed_now"] = get_global_gate() is not None
    out["dry_run"] = True
    return out


def resolve_locked_live_task(
    task_manifest: str,
    *,
    task_index: int = 0,
    split: str = "valid_train",
) -> Dict[str, Any]:
    """Manifest lock sequence shared by live entry and tests.

    Read manifest -> SHA256 -> select exact task -> assert split membership
    -> resolve exact game file. No LLM call, no random fallback.
    """
    from src.benchmark.manifest_lock import (
        assert_task_in_split,
        canonical_game_id,
        load_manifest,
        manifest_sha256,
        select_task,
    )
    from src.benchmark.split_integrity import resolve_split

    mf_path = Path(task_manifest)
    if not mf_path.exists():
        raise SystemExit(f"manifest missing: {mf_path}")
    mf = load_manifest(mf_path)
    mf_sha = manifest_sha256(mf_path)
    task = select_task(mf, int(task_index))
    resolve_split(split)  # fail-closed split name
    assert_task_in_split(task, split)  # task itself must lie in split
    game_file = str(task["game_id"])
    if not game_file.endswith("game.tw-pddl"):
        game_file = game_file.rstrip("/") + "/game.tw-pddl"
    raw_task_id = str(task.get("game_id") or task.get("fingerprint") or task_index)
    return {
        "manifest_path": str(mf_path),
        "manifest_sha256": mf_sha,
        "task_index": int(task_index),
        "split": split,
        "task": task,
        "game_file": game_file,
        "raw_task_id": raw_task_id,
        "target_game_id": str(task["game_id"]),
        "target_canonical_id": canonical_game_id(str(task["game_id"])),
    }


def make_locked_reset(env, game_file: str, target_game_id: str):
    """reset wrapper: forced game + canonical identity check every reset."""
    from src.benchmark.manifest_lock import verify_actual_matches_target

    def locked_reset(episode_index: int = 0):
        obs, infos = env.reset(episode_index=episode_index, force_game_file=game_file)
        actual = env.last_reset_meta.get("actual_game_id", "")
        verify_actual_matches_target(actual, target_game_id)
        return obs, infos

    return locked_reset


def live_run(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.live:
        raise SystemExit("refusing live run without --live")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY missing")
    from src.benchmark.manifest_lock import canonical_game_id, verify_actual_matches_target
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.live_launcher import launch_live_experiment

    # --- Manifest lock BEFORE any LLM request ---
    lock = resolve_locked_live_task(
        args.task_manifest,
        task_index=int(getattr(args, "task_index", 0)),
        split=args.split,
    )
    game_file = lock["game_file"]
    task = lock["task"]

    env = NativeALFWorldEnv(
        NativeALFWorldConfig(split=args.split, num_games=200, max_steps=args.horizon)
    )
    locked_reset = make_locked_reset(env, game_file, lock["target_game_id"])
    locked_reset(0)  # identity verified before first LLM call
    actual_id = env.last_reset_meta.get("actual_game_id", "")
    can_id = canonical_game_id(actual_id)
    verify_actual_matches_target(actual_id, lock["target_game_id"])

    launch = launch_live_experiment(
        experiment_id=args.experiment_id,
        ledger_path=args.ledger_path,
        max_physical=args.physical_cap,
        max_cost_usd=args.cost_cap,
    )
    from src.agent.genome import AgentGenome
    from src.runtime.episode_runner import EpisodeRunner

    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 64)

    def llm(prompt: str):
        resp = launch["backend"].generate(prompt, budget=8)
        return {"text": resp.text, "usage": {"calls": 1, "tokens_in": resp.tokens_prompt,
                                            "tokens_out": resp.tokens_completion, "cost": resp.cost},
                "model": resp.model}

    git_sha = _git_sha()
    runner = EpisodeRunner(genome, llm, horizon=args.horizon, model="deepseek-flash",
                           experiment_id=args.experiment_id,
                           git_sha=git_sha)
    out = runner.run(locked_reset, env.step, episode_id=0, seed=args.seed)
    out["manifest_sha256"] = lock["manifest_sha256"]
    out["selected_manifest_game_id"] = lock["target_game_id"]
    out["raw_task_id"] = lock["raw_task_id"]
    out["canonical_game_id"] = can_id
    out["task_index"] = lock["task_index"]
    out["requested_split"] = lock["split"]
    outp = Path(args.output_dir) / "pilot1_episode.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "episode": out,
        "ledger": launch["db"].snapshot(),
        "manifest_sha256": lock["manifest_sha256"],
        "raw_task_id": lock["raw_task_id"],
        "actual_game_id": actual_id,
        "canonical_game_id": can_id,
        "git_sha": git_sha,
    }


def _git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip()
    except Exception:
        return "unknown"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--mode", default="pilot1_wiring")
    ap.add_argument("--experiment-id", default="pilot1")
    ap.add_argument("--ledger-path", default="results/pilot1_hotfix_offline/budget.sqlite")
    ap.add_argument("--physical-cap", type=int, default=120)
    ap.add_argument("--cost-cap", type=float, default=0.05)
    ap.add_argument("--task-manifest", default="results/native_alfworld/development_task_pool.json")
    ap.add_argument("--task-index", type=int, default=0)
    ap.add_argument("--output-dir", default="results/pilot1_hotfix_offline")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--split", default="valid_train")
    ap.add_argument("--horizon", type=int, default=30)
    args = ap.parse_args()

    if args.dry_run:
        result = dry_run(args)
    else:
        result = live_run(args)
    outp = Path(args.output_dir) / ("dry_run.json" if args.dry_run else "live_result.json")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False)[:2000])
    print("WROTE", outp)


if __name__ == "__main__":
    main()
