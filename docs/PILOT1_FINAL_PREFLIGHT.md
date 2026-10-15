# Pilot 1 Final Preflight

**Scope:** last configuration correction before real Pilot 1 — pricing, transport
uncertainty safety, Docker git identity. Not a new research phase.

**Real DeepSeek API calls this phase: 0.**  
**Research frozen:** NSGA-III · PEEM · PPEC · Agent Genome · `candidate_2obj`.

---

## Fix 1 — Official DeepSeek pricing (conservative peak)

Source: https://api-docs.deepseek.com/quick_start/pricing/ (verified 2026-10)

Official model id: **`deepseek-flash`** (DeepSeek-V4.1-Flash)

| Item | Peak $/1M | Off-peak $/1M |
|---|---:|---:|
| Input, cache hit | 0.006 | 0.003 |
| Input, cache miss | **0.30** | 0.15 |
| Output | **1.20** | 0.60 |

Pilot policy — **peak conservative** (never under-budget):

```python
PEAK_INPUT_CACHE_MISS_PER_1M = 0.30
PEAK_OUTPUT_PER_1M = 1.20
RATE_VERSION = "deepseek-flash-2026-10-peak-conservative-v1"
```

Fixed check (`prompt=100`, `completion=20`):

```
100 * 0.30 / 1e6 + 20 * 1.20 / 1e6 = $0.000054
```

**Single authority:** `src/backend/rates.py`. `cost_status.py` imports it;
`base.py` / `api_budget.py` / transport / episode / SQLite all price through
that path. Retired name `deepseek-chat` is **not** priced (UNKNOWN_RATE) —
unknown models never fall back to cheaper rates.

This is a **local budget estimate**, not the provider invoice.

**Reservation policy:** pre-send reservation uses explicit token upper bounds
(`2000` prompt + `128` completion) × peak rates ≈ `$0.000754`/request —
not average-cost guessing. Caps unchanged: **physical HTTP ≤ 120 ·
estimated cost ≤ $0.05**.

## Fix 2 — Transport uncertainty = atomic billing block

Timeout / dropped connection after a send is **not** proof of zero cost.

```
Physical attempt → Timeout / response lost
        ↓
TRANSPORT_UNCERTAIN
        ↓
settle_unknown_and_block()   # one BEGIN IMMEDIATE
        ↓
BillingBlocked → experiment aborts (no retry)
```

| Case | Treatment |
|---|---|
| Local pre-send failure (e.g. curl missing) | settle failed, **no** block |
| Timeout / reset / partial read after send | `TRANSPORT_UNCERTAIN` block |
| Missing usage / unknown model on a response | `UNKNOWN_USAGE` / `UNKNOWN_RATE` block |
| Known cost response | normal settle |

`BudgetDB.settle_unknown_and_block` keeps: physical attempt count, exactly-once
ticket settlement, persistent `billing_blocked=1`, prior ledger rows intact.

Evidence: `results/pilot1_preflight/timeout_billing_block.json`

```
physical_attempts = 1
billing_blocked   = true
second_physical_send = 0
block survives SQLite reopen
```

## Fix 3 — Accurate Git SHA in Docker

Host resolves SHA and passes `GIT_SHA` into the container. Container validates
via `src/runtime/run_identity.resolve_git_sha()`:

- must be 40 hex chars
- rejects `unknown`, `docker`, `HEAD`, short/non-hex values
- refuses run-manifest write with an invalid SHA

Docker (PowerShell) actually used:

```powershell
$sha = git rev-parse HEAD
docker run --rm -v alfworld-data:/data `
  -v "D:\新建文件夹\src:/src" -v "D:\新建文件夹\scripts:/scripts" `
  -v "D:\新建文件夹\results:/results" `
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ -e GIT_SHA=$sha `
  alfworld-local:tw python /scripts/native_offline_smoke.py
```

Result: container recorded
`git_sha = c3580e31f25ec67a44bf6cd04efcbd183f61ebac` (= host HEAD) —
see `results/pilot1_preflight/docker_git_identity.json`.

Run manifest fields written: `git_sha`, `manifest_sha256`, `experiment_id`,
`model`, `rate_version`, `task_index`, `seed`, `objective_version`.

## Files touched

```
src/backend/rates.py          # single authoritative rate table
src/backend/cost_status.py    # imports rates
src/backend/base.py           # no cheap unknown-model fallback
src/backend/http_client.py    # TRANSPORT_UNCERTAIN atomic block
src/runtime/live_launcher.py  # peak-based reservation
src/runtime/api_budget.py     # same rates
src/runtime/run_identity.py   # GIT_SHA validation + run manifest
scripts/pilot1_entry.py
scripts/native_offline_smoke.py
tests/test_pilot1_preflight.py
```

**Not modified:** `nsga3.py`, `pareto_credit.py`, `credit_assignment.py`,
`preference_2d.py`, Genome, ObjectiveSpec, historical result JSONs.
