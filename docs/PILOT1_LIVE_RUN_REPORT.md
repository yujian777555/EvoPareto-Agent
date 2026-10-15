# Pilot 1 Live Run Report — DeepSeek + ALFWorld

**Authorization:** `APPROVED_LIVE_PILOT1`  
**Git SHA (executed):** `e80753a84a3d650383ea1ec35516cd2513cbe910`  
**Run count:** exactly **1** (no second attempt)  
**Purpose:** engineering wiring validation — **NOT** PEEM/PPEC performance evidence

---

## 1. Identity

| Field | Value |
|---|---|
| experiment_id | `pilot1` |
| model | `deepseek-flash` |
| rate_version | `deepseek-flash-2026-10-peak-conservative-v1` |
| objective_version | `candidate_2obj` (performance↑, cost↓) |
| manifest_sha256 | `27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7` |
| task_index | 0 |
| selected_manifest_game_id | `/data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990` |
| actual/canonical game | same (force_game_file + canonical match, verified before first request) |
| split | `valid_train` (requested = actual) |
| goal | look at book under the desklamp. |
| seed | 11 |
| genome | cot / short_term / self_critique / balanced / budget=64 |

## 2. Outcome (honest)

| Metric | Value |
|---|---|
| **native `won`** | **false** |
| success | false |
| termination_reason | `budget_exhausted` (agent reasoning budget, not HTTP budget) |
| episode steps | 29 |
| logical LLM calls | 30 (30 actions + 1 reflection) |
| physical HTTP attempts | **30** / cap 120 |
| tokens_in | 8418 |
| tokens_out | 122 |
| **estimated cost** | **$0.0026718** / cap $0.05 |
| retries | 0 |
| open tickets | 0 |
| settled_ok / settled_failed | 30 / 0 |
| billing_blocked | **none** |
| unknown cost events | **none** |

Cost check (peak conservative, exact):

```
8418 × $0.30/1M + 122 × $1.20/1M = $0.0026718
ledger.spent_cost == episode.cost_usd == 0.0026718   ✓
```

Per-request reservation used `0.0007536` (2000 in + 128 out × peak rates);
released and settled with actual usage every call. Local $0.05 is an estimate
cap, not a provider invoice.

## 3. Trajectory summary

Agent entered a look/examine loop around `desk 1` / `shelf 1` and never
executed `look at book under the desklamp` before the reasoning budget ran
out at step 29. All `won` flags in the trace are `false` — no fabricated
success. Full 29-step trace preserved in
`results/pilot1_live_run/pilot1_episode.json`.

## 4. Stop reason

Natural end of episode (agent budget exhausted after 29 steps).  
**No** BillingBlocked, **no** BudgetExceeded, **no** identity mismatch,
**no** transport-uncertain event. Ledger left in a consistent state.

## 5. Commands (PowerShell, host)

```powershell
$sha = git rev-parse HEAD   # e80753a84a3d650383ea1ec35516cd2513cbe910
docker run --rm -v alfworld-data:/data `
  -v "<repo>/src:/src" -v "<repo>/scripts:/scripts" -v "<repo>/results:/results" `
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ -e GIT_SHA=$sha -e DEEPSEEK_API_KEY `
  alfworld-local:tw python /scripts/pilot1_entry.py --live `
    --experiment-id pilot1 `
    --ledger-path /results/pilot1_live_run/budget.sqlite `
    --physical-cap 120 --cost-cap 0.05 `
    --task-manifest /results/native_alfworld/development_task_pool.json `
    --task-index 0 `
    --output-dir /results/pilot1_live_run `
    --split valid_train --horizon 30 --seed 11
```

## 6. Artifacts

```
results/pilot1_live_run/
  live_result.json        # episode + ledger snapshot
  pilot1_episode.json     # full 29-step trajectory
  budget.sqlite           # persistent ticket ledger
  run_manifest.json       # git_sha / manifest_sha256 / rate_version / ...
  docker_live_stdout.txt  # container stdout
  dry_run.json            # pre-flight inside same container
  audit_report.json       # structured audit
```

## 7. Interpretation limits

This single episode validates the **engineering chain** only:

manifest lock → native ALFWorld reset → DeepSeek HTTP with ticket accounting →
SQLite ledger → episode cost reconciliation.

It is **not** evidence of PEEM, PPEC, or NSGA-III algorithmic advantage.
`won=false` on this task is an honest negative, not a defect in the pipeline.

**Executor stops here.** Awaiting Planner analysis — no second Pilot.
