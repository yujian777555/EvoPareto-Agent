"""Stage 1 feasibility runner: 3 tasks x 3 genomes x 2 seeds = 18 episodes.

Loads genomes ONLY from the frozen experiment_config.json (never hardcodes).
Shares one SQLite budget ledger for the whole batch. Fail-closed.
Real DeepSeek + native ALFWorld. Docker entrypoint.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_frozen_config(path: str) -> Dict[str, Any]:
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("genomes", "frozen_tasks", "seeds", "budget_caps", "manifest_sha256"):
        if key not in cfg:
            raise SystemExit(f"experiment_config missing {key}")
    return cfg


def load_matrix(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    combos = data["combinations"]
    if len(combos) != 18:
        raise SystemExit(f"matrix must have exactly 18 combinations, got {len(combos)}")
    seen = set()
    for c in combos:
        key = (c["task_index"], c["genome_id"], c["seed"])
        if key in seen:
            raise SystemExit(f"duplicate combination {key}")
        seen.add(key)
    return combos


def genome_from_config(cfg: Dict[str, Any], genome_id: str) -> Dict[str, Any]:
    for g in cfg["genomes"]:
        if g["id"] == genome_id:
            return g
    raise SystemExit(f"genome {genome_id} not in frozen config")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment-config", required=True)
    ap.add_argument("--experiment-matrix", required=True)
    ap.add_argument("--ledger-path", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--exec-sha", required=True, help="40-hex git SHA of the execution code")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import re

    if not re.fullmatch(r"[0-9a-f]{40}", args.exec_sha):
        print("FATAL: --exec-sha must be 40 hex")
        return 2

    cfg = load_frozen_config(args.experiment_config)
    matrix = load_matrix(args.experiment_matrix)
    outdir = Path(args.output_dir)
    epdir = outdir / "episodes"
    epdir.mkdir(parents=True, exist_ok=True)

    caps = cfg["budget_caps"]
    run_manifest = {
        "stage": "STAGE1_FEASIBILITY",
        "exec_git_sha": args.exec_sha,
        "manifest_sha256": cfg["manifest_sha256"],
        "rate_version": cfg["rate_version"],
        "objective_version": cfg["objective_version"],
        "model": cfg["model"],
        "horizon": cfg["horizon"],
        "split": cfg["split"],
        "budget_caps": caps,
        "n_matrix": len(matrix),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (outdir / "run_manifest.json").write_text(
        json.dumps(run_manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_OK", "n": len(matrix)}, indent=2))
        return 0

    # ---- real path ----
    from src.agent.genome import AgentGenome
    from src.benchmark.manifest_lock import (
        canonical_game_id,
        load_manifest,
        manifest_sha256,
        select_task,
        verify_actual_matches_target,
    )
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.backend.rates import RATE_VERSION
    from src.runtime.episode_runner import EpisodeRunner
    from src.runtime.http_budget import BillingBlocked, BudgetDB, PhysicalBudgetGate, install_global_gate
    from src.runtime.live_launcher import launch_live_experiment
    from src.runtime.run_identity import resolve_git_sha, write_run_manifest as write_identity

    git_sha = resolve_git_sha()
    if git_sha != args.exec_sha:
        print(f"FATAL: GIT_SHA {git_sha} != --exec-sha {args.exec_sha}")
        return 2

    if RATE_VERSION != cfg["rate_version"]:
        print(f"FATAL: rate_version mismatch {RATE_VERSION} vs {cfg['rate_version']}")
        return 2

    mf_path = Path("/results/native_alfworld/development_task_pool.json")
    if not mf_path.exists():
        mf_path = Path(cfg["manifest_path"])
    mf = load_manifest(mf_path)
    actual_mf_sha = manifest_sha256(mf_path)
    if actual_mf_sha != cfg["manifest_sha256"]:
        print(f"FATAL: manifest sha mismatch {actual_mf_sha}")
        return 2

    # Shared batch ledger
    launch = launch_live_experiment(
        experiment_id="stage1_feasibility",
        ledger_path=args.ledger_path,
        max_physical=caps["physical_http_cap"],
        max_cost_usd=caps["estimated_cost_cap_usd"],
    )
    db = launch["db"]

    status_rows: List[Dict[str, Any]] = []
    n_done = 0
    n_success = 0
    stopped_reason = ""

    for cell in matrix:
        snap = db.snapshot()
        if snap["physical_attempts"] >= snap["max_physical"]:
            stopped_reason = "physical_http_cap"
            break
        if snap["spent_cost_usd"] >= snap["max_cost_usd"]:
            stopped_reason = "cost_cap"
            break
        if db.is_billing_blocked():
            stopped_reason = "billing_blocked"
            break

        gcfg = genome_from_config(cfg, cell["genome_id"])
        task = select_task(mf, int(cell["task_index"]))
        game_file = str(task["game_id"])
        if not game_file.endswith("game.tw-pddl"):
            game_file = game_file.rstrip("/") + "/game.tw-pddl"
        verify_actual_matches_target(str(task["game_id"]), str(task["game_id"]))

        genome = AgentGenome(
            gcfg["planner_strategy"],
            gcfg["memory_strategy"],
            gcfg["reflection_strategy"],
            gcfg["tool_policy"],
            int(gcfg["reasoning_budget"]),
        )
        # genome in episode must equal frozen config
        if genome.to_dict() != {k: gcfg[k] for k in (
            "planner_strategy", "memory_strategy", "reflection_strategy",
            "tool_policy", "reasoning_budget",
        )}:
            print(f"FATAL: genome mismatch for {cell['genome_id']}")
            return 2

        env = NativeALFWorldEnv(
            NativeALFWorldConfig(split=cfg["split"], num_games=200, max_steps=cfg["horizon"])
        )

        def locked_reset(episode_index=0, _gf=game_file, _tg=str(task["game_id"])):
            obs, infos = env.reset(episode_index=episode_index, force_game_file=_gf)
            verify_actual_matches_target(
                env.last_reset_meta.get("actual_game_id", ""), _tg
            )
            return obs, infos

        def llm(prompt: str):
            resp = launch["backend"].generate(prompt, budget=8)
            return {
                "text": resp.text,
                "usage": {
                    "calls": 1,
                    "tokens_in": resp.tokens_prompt,
                    "tokens_out": resp.tokens_completion,
                    "cost": resp.cost,
                },
                "model": resp.model,
            }

        runner = EpisodeRunner(
            genome, llm,
            horizon=cfg["horizon"],
            model=cfg["model"],
            experiment_id="stage1_feasibility",
            git_sha=git_sha,
        )
        t0 = time.time()
        row: Dict[str, Any] = {
            "episode_id": cell["episode_id"],
            "exec_order": cell["exec_order"],
            "task_index": cell["task_index"],
            "genome_id": cell["genome_id"],
            "seed": cell["seed"],
            "game_id": cell["game_id"],
            "genome_config": gcfg,
        }
        try:
            ep = runner.run(locked_reset, env.step, episode_id=0, seed=int(cell["seed"]))
            ep["episode_id"] = cell["episode_id"]
            ep["genome_id"] = cell["genome_id"]
            ep["task_index"] = cell["task_index"]
            ep["exec_git_sha"] = git_sha
            ep["manifest_sha256"] = actual_mf_sha
            # genome consistency check
            for k in ("planner_strategy", "memory_strategy", "reflection_strategy",
                      "tool_policy", "reasoning_budget"):
                if ep["genome"].get(k) != gcfg[k]:
                    print(f"FATAL: episode genome field {k} mismatch")
                    return 2
            row.update({
                "status": "completed",
                "won": bool(ep["success"]),
                "steps": ep["steps"],
                "llm_call_count": ep["llm_call_count"],
                "reflection_count": ep.get("reflection_count"),
                "tokens_in": ep["tokens_in"],
                "tokens_out": ep["tokens_out"],
                "cost_usd": ep["cost_usd"],
                "termination_reason": ep["termination_reason"],
                "n_decision_logs": len(ep.get("decision_logs") or []),
            })
            if ep["success"]:
                n_success += 1
            (epdir / f"{cell['episode_id']}.json").write_text(
                json.dumps(ep, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except BillingBlocked as e:
            row.update({"status": "billing_blocked", "error": str(e)})
            stopped_reason = "billing_blocked"
            (epdir / f"{cell['episode_id']}.json").write_text(
                json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            status_rows.append(row)
            n_done += 1
            break
        except Exception as e:
            row.update({"status": "error", "error": f"{type(e).__name__}: {e}"})
            (epdir / f"{cell['episode_id']}.json").write_text(
                json.dumps(row, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        row["wall_seconds"] = round(time.time() - t0, 3)
        status_rows.append(row)
        n_done += 1
        snap = db.snapshot()
        print(
            f"[{cell['exec_order']:2d}/18] {cell['episode_id']} "
            f"won={row.get('won')} steps={row.get('steps')} "
            f"http={snap['physical_attempts']} cost={snap['spent_cost_usd']:.6f}"
        )

    snap = db.snapshot()
    summary = {
        "executed_episodes": n_done,
        "successful_episodes": n_success,
        "stopped_reason": stopped_reason or "matrix_completed",
        "ledger": snap,
        "billing_blocked": db.is_billing_blocked(),
        "billing_block_reason": db.billing_block_reason() if db.is_billing_blocked() else "",
        "exec_git_sha": git_sha,
        "manifest_sha256": actual_mf_sha,
        "episodes": status_rows,
    }
    (outdir / "raw_episode_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_identity(
        outdir / "run_identity.json",
        git_sha=git_sha,
        manifest_sha256=actual_mf_sha,
        experiment_id="stage1_feasibility",
        model=cfg["model"],
        rate_version=cfg["rate_version"],
        task_index=0,
        seed=0,
        objective_version=cfg["objective_version"],
        extra={"n_executed": n_done, "n_success": n_success},
    )
    print(json.dumps({"executed": n_done, "success": n_success, "stopped": summary["stopped_reason"],
                      "http": snap["physical_attempts"], "cost": snap["spent_cost_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
