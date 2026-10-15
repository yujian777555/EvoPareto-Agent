# Pilot 1 Live Admission Final Patch

**Scope:** local admission patch only — live manifest lock, atomic billing, HTTP↔SQLite reconciliation.  
**Research frozen:** NSGA-III · PEEM · PPEC · Agent Genome · `candidate_2obj`.  
**Real DeepSeek API calls this phase:** **0**.

Git base: `f0db3af` → this patch. Objective unchanged:

```python
objective_version = "candidate_2obj"
objective_names = ("performance", "cost")
maximize = (True, False)
```

---

## P0-1 Manifest lock on the live entry

`scripts/pilot1_entry.py` now runs the same verified sequence as
`scripts/native_offline_smoke.py` before any LLM request:

```
Read frozen manifest
      ↓
Validate manifest SHA256
      ↓
select_task(task_index)          # explicit, reproducible (default 0)
      ↓
resolve_split(split)             # fail-closed split name
      ↓
assert_task_in_split(task, split) # task must lie in valid_train
      ↓
Resolve exact game file (…/game.tw-pddl)
      ↓
NativeALFWorldEnv.reset(force_game_file=…)
      ↓
verify_actual_matches_target(actual, target)   # full canonical ID
      ↓
PASS → permit first DeepSeek request
```

Shared helpers (no algorithm re-implementation):

- `resolve_locked_live_task(...)` — manifest → SHA256 → select → split → game file
- `make_locked_reset(env, game_file, target)` — every reset forces the same
  game file and re-checks canonical identity (EpisodeRunner's own reset goes
  through this wrapper, so a second reset cannot change the task)

Failures:

| Condition | Behaviour |
|---|---|
| manifest file missing | `SystemExit` before any network |
| task not in `valid_train` | `ValueError` |
| actual game ≠ manifest target | `RuntimeError` (identity mismatch) |
| wrong game forced | rejected by `verify_actual_matches_target` |

Episode log fields written: `manifest_sha256`, `selected_manifest_game_id`,
`raw_task_id`, `canonical_game_id`, `task_index`, `requested_split`, `git_sha`.

CLI: `--task-manifest` is mandatory for live identity; `--task-index` selects
the frozen task (Pilot 1 fixes `task_index=0`).

## P0-2 Atomic unknown-cost billing block

### `BudgetDB.settle_unknown_and_block(ticket, reason, tokens_in, tokens_out)`

One `BEGIN IMMEDIATE` transaction:

1. verify ticket exists and is still `open`
2. mark ticket `settled` (physical attempt recorded exactly once)
3. release reservation, add tokens, `settled_failed += 1`
4. write `billing_blocked=1`, `billing_block_reason`, `unknown_cost_ticket_id`
5. `COMMIT`

No separate `mark_billing_blocked()` call after settle. Commit failure
propagates — the caller aborts.

### `acquire_ticket` race fix

Billing-block check now runs **inside** `BEGIN IMMEDIATE`, before any
reservation:

```
BEGIN IMMEDIATE
      ↓
Check billing_blocked     ← cannot be bypassed by another process
      ↓
Check physical / cost budget
      ↓
Reserve ticket
      ↓
COMMIT
```

All transaction failure paths use quiet single ROLLBACK (no double-rollback
`OperationalError` that previously masked `BillingBlocked`).

### `http_client.post_json`

- **One physical send per try** — transport chosen once (curl if present else
  urllib). The old curl→urllib fallback double-fired mock/real endpoints.
- Unknown cost → `settle_unknown_and_block` then raise `BillingBlocked`
  (never presented as a zero-cost success).
- No gate + unknown cost → abort; unknown is never written as certain zero.
- `BillingBlocked` / `BudgetExceeded` / `GateRequired` never retry.
- Transport failure settles the ticket once (flag-guarded, no double settle).

Budget caps unchanged: **physical HTTP ≤ 120 · estimated cost ≤ $0.05**.

## P0-3 HTTP → Backend → Episode → SQLite reconciliation

Real chain exercised by `tests/test_pilot1_final_patch.py` with a local mock
DeepSeek HTTP server:

```
Local mock HTTP server
      ↓  real post_json()
PhysicalBudgetGate → SQLite ticket
      ↓  simulated DeepSeek JSON (frozen rates)
DeepSeekBackend.generate()
      ↓
EpisodeRunner
      ↓
SQLite reconciliation
```

Single-success scenario verified equalities:

```
ledger.tokens_in   == backend.total_prompt_tokens   == 100
ledger.tokens_out  == backend.total_completion_tokens == 20
ledger.spent_cost  == backend.total_cost            == episode.cost_usd
                 == frozen rate formula (deepseek-flash-2026-v1)
physical HTTP hits == 1 · logical LLM calls == 1 · tickets settled once
```

Failure paths covered: 200+empty completion, 401/402/429, timeout, missing
usage, unknown model. Missing usage → atomic block → **second network send
count = 0**.

## Files touched (scope-limited)

```
scripts/pilot1_entry.py
scripts/native_offline_smoke.py        # dual-write evidence paths
src/backend/http_client.py
src/runtime/http_budget.py
tests/test_pilot1_final_patch.py
results/pilot1_live_admission_verified/*
```

Not modified: `nsga3.py`, `pareto_credit.py`, `credit_assignment.py`,
`preference_2d.py`, Genome, ObjectiveSpec.
