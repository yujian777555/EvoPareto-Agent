"""Stage 1.8 live A/B runner: 6 episodes (3 tasks x 2 runtimes x 1 G1)."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment-config", required=True)
    ap.add_argument("--experiment-matrix", required=True)
    ap.add_argument("--ledger-path", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--exec-sha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.exec_sha):
        print("FATAL: bad exec-sha")
        return 2
    cfg = json.loads(Path(args.experiment_config).read_text(encoding="utf-8"))
    matrix = json.loads(Path(args.experiment_matrix).read_text(encoding="utf-8"))["combinations"]
    if len(matrix) != 6:
        print("FATAL: need 6 cells")
        return 2
    outdir = Path(args.output_dir)
    epdir = outdir / "episodes"
    epdir.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        print(json.dumps({"status": "DRY_RUN_OK", "n": len(matrix)}))
        return 0

    from src.agent.genome import AgentGenome
    from src.benchmark.manifest_lock import load_manifest, manifest_sha256, select_task
    from src.benchmark.native_alfworld import NativeALFWorldConfig, NativeALFWorldEnv
    from src.runtime.episode_runner import EpisodeRunner
    from src.runtime.http_budget import BillingBlocked
    from src.runtime.live_launcher import launch_live_experiment
    from src.runtime.run_identity import resolve_git_sha

    git_sha = resolve_git_sha()
    if git_sha != args.exec_sha:
        print("FATAL: sha mismatch")
        return 2
    mf_path = Path("/results/native_alfworld/development_task_pool.json")
    if not mf_path.exists():
        mf_path = Path("results/native_alfworld/development_task_pool.json")
    mf = load_manifest(mf_path)
    mf_sha = manifest_sha256(mf_path)
    if mf_sha != cfg["manifest_sha256"]:
        print("FATAL: manifest sha mismatch")
        return 2

    g = cfg["genome"]
    genome = AgentGenome(g["planner_strategy"], g["memory_strategy"],
                         g["reflection_strategy"], g["tool_policy"], int(g["reasoning_budget"]))
    caps = cfg["budget_caps"]
    launch = launch_live_experiment(
        experiment_id="stage1_8", ledger_path=args.ledger_path,
        max_physical=caps["physical_http_cap"], max_cost_usd=caps["estimated_cost_cap_usd"])
    db = launch["db"]

    (outdir / "run_manifest.json").write_text(json.dumps({
        "exec_git_sha": git_sha, "manifest_sha256": mf_sha,
        "budget_caps": caps, "genome": g,
        "prompt_template": cfg.get("prompt_template"),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    rows = []
    n_done = n_cur = n_grd = 0
    stopped = ""
    for cell in matrix:
        snap = db.snapshot()
        if snap["physical_attempts"] >= snap["max_physical"]:
            stopped = "physical_http_cap"
            break
        if snap["spent_cost_usd"] >= snap["max_cost_usd"]:
            stopped = "cost_cap"
            break
        if db.is_billing_blocked():
            stopped = "billing_blocked"
            break
        task = select_task(mf, int(cell["task_index"]))
        game_file = str(task["game_id"])
        if not game_file.endswith("game.tw-pddl"):
            game_file = game_file.rstrip("/") + "/game.tw-pddl"
        env = NativeALFWorldEnv(NativeALFWorldConfig(split="valid_train", num_games=200, max_steps=30))

        def locked_reset(episode_index=0, _gf=game_file):
            return env.reset(episode_index=episode_index, force_game_file=_gf)

        def llm(prompt: str):
            resp = launch["backend"].generate(prompt, budget=8)
            return {"text": resp.text, "usage": {"calls": 1, "tokens_in": resp.tokens_prompt,
                                                 "tokens_out": resp.tokens_completion, "cost": resp.cost},
                    "model": resp.model}

        variant = cell["runtime_variant"]
        runner = EpisodeRunner(genome, llm, horizon=cfg["horizon"], model=cfg["model"],
                               experiment_id="stage1_8", git_sha=git_sha, runtime_variant=variant)
        t0 = time.time()
        row = {"episode_id": cell["episode_id"], "exec_order": cell["exec_order"],
               "task_index": cell["task_index"], "runtime_variant": variant,
               "genome_id": "G1", "game_id": cell["game_id"]}
        try:
            ep = runner.run(locked_reset, env.step, episode_id=0, seed=0)
            ep["episode_id"] = cell["episode_id"]
            ep["runtime_variant"] = variant
            ep["exec_git_sha"] = git_sha
            ep["manifest_sha256"] = mf_sha
            row.update({"status": "completed", "won": bool(ep["success"]),
                        "steps": ep["steps"], "llm_call_count": ep["llm_call_count"],
                        "tokens_in": ep["tokens_in"], "tokens_out": ep["tokens_out"],
                        "cost_usd": ep["cost_usd"],
                        "termination_reason": ep["termination_reason"],
                        "wall_seconds": round(time.time() - t0, 3)})
            if ep["success"]:
                if variant == "current":
                    n_cur += 1
                else:
                    n_grd += 1
            (epdir / f"{cell['episode_id']}.json").write_text(
                json.dumps(ep, indent=2, ensure_ascii=False), encoding="utf-8")
        except BillingBlocked as e:
            row.update({"status": "billing_blocked", "error": str(e)})
            stopped = "billing_blocked"
            (epdir / f"{cell['episode_id']}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
            rows.append(row)
            n_done += 1
            break
        except Exception as e:
            row.update({"status": "error", "error": f"{type(e).__name__}: {e}",
                        "wall_seconds": round(time.time() - t0, 3)})
            (epdir / f"{cell['episode_id']}.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
        rows.append(row)
        n_done += 1
        snap = db.snapshot()
        print(f"[{cell['exec_order']}/6] {cell['episode_id']} won={row.get('won')} "
              f"steps={row.get('steps')} http={snap['physical_attempts']} cost={snap['spent_cost_usd']:.6f}")

    snap = db.snapshot()
    (outdir / "raw_episode_summary.json").write_text(json.dumps({
        "executed_episodes": n_done, "current_success": n_cur, "grounded_success": n_grd,
        "stopped_reason": stopped or "matrix_completed", "ledger": snap,
        "billing_blocked": db.is_billing_blocked(), "exec_git_sha": git_sha,
        "episodes": rows,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"executed": n_done, "current": n_cur, "grounded": n_grd,
                      "stopped": stopped or "done", "http": snap["physical_attempts"],
                      "cost": snap["spent_cost_usd"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
