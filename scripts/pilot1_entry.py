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


def live_run(args: argparse.Namespace) -> Dict[str, Any]:
    if not args.live:
        raise SystemExit("refusing live run without --live")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY missing")
    from src.runtime.live_launcher import launch_live_experiment

    launch = launch_live_experiment(
        experiment_id=args.experiment_id,
        ledger_path=args.ledger_path,
        max_physical=args.physical_cap,
        max_cost_usd=args.cost_cap,
    )
    # Native episode smoke: 1 genome × 1 episode only (engineering).
    from src.agent.genome import AgentGenome
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.episode_runner import EpisodeRunner

    env = NativeALFWorldEnv(NativeALFWorldConfig(split=args.split, num_games=1, max_steps=args.horizon))
    genome = AgentGenome("cot", "short_term", "self_critique", "balanced", 64)

    def llm(prompt: str):
        resp = launch["backend"].generate(prompt, budget=8)
        return {"text": resp.text, "usage": {"calls": 1, "tokens_in": resp.tokens_prompt,
                                            "tokens_out": resp.tokens_completion, "cost": resp.cost},
                "model": resp.model}

    runner = EpisodeRunner(genome, llm, horizon=args.horizon, model="deepseek-flash",
                           experiment_id=args.experiment_id)
    out = runner.run(env.reset, env.step, episode_id=0, seed=args.seed)
    outp = Path(args.output_dir) / "pilot1_episode.json"
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"episode": out, "ledger": launch["db"].snapshot()}


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
