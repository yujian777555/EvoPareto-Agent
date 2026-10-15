# Pilot1 Manifest & Billing Fix

## Manifest lock (P0-A)

**Bug:** `manifest_game_match=false` but `native_dry_run_status=PASS`.

**Fix:**
- `manifest_lock.py` — `canonical_game_id` (trial-dir ↔ game.tw-pddl), sha256, select_task
- `NativeALFWorldEnv.reset(force_game_file=...)` loads **exact** manifest game
- Smoke PASS requires **all** of: importable, manifest_valid, **manifest_game_match**,
  reset, step, episode, fitness_2d, writable

**Evidence:** `results/pilot1_final_admission_verified/native_smoke.json`  
selected == actual (`.../look_at_obj_in_light-Book-None-DeskLamp-302/...`) · **PASS**

## Billing block (P0-B)

Unknown cost (`UNKNOWN_USAGE` / `UNKNOWN_RATE`) → `BudgetDB.mark_billing_blocked`
persisted in SQLite `meta`. `acquire_ticket` raises `BillingBlocked` **before**
network; survives restart (`test_unknown_cost_billing_block_persists`).

## Scope

Only backend/http_budget/native_alfworld/split/manifest + scripts/tests.  
NSGA-III / PEEM / PPEC untouched. **0 real API.**
