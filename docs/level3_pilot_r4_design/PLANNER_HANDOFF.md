# LEVEL3-PILOT-R4 R6 — Planner Handoff

**Start:** `877fc0d2cb8097fa91da599f155b7ee921f348f0`  
**Real API:** **0** · Auth read-only · Historical results unmodified

---

## P0 — budget bypass (Task A)

| Control | Implementation |
|---|---|
| Policy in **code** | `src/research/r4_budget_policy.py` `R4-BUDGET-POLICY-v1` |
| Hash-recompute bypass | config must match POLICY; tests lower every numeric + rehash → **REJECT** |
| Type/NaN/inf | `BUDGET_POLICY_TYPE/NOT_FINITE` |
| planned R vs seeds | `BUDGET_PLANNED_R_NEQ_SEEDS` / `NEQ_PLAN_SEEDS` |
| Remaining quota | demand vs `max−consumed`; missing remaining → fail closed |
| HTTP block | `verify_execution_allowed`: PROPOSED → `EXEC_STATUS_BLOCKS_HTTP` even with loose auth |
| Zero model calls in gates | no HTTP imports; tests assert |

**R=6 / R=10 rejected before any HTTP** (`need=1848/2904`, `remaining=56`).

## Task B — contamination audit

* Precise path exclusions with SHA/size/reason (`exclusion_log`); unknown same basename **not** excluded.
* `PHASE2_EVOLUTION_MEMORY.md` mixed UTF-8/Big5 — **encoding not reliably identifiable** → remains required-text **BLOCKED** (honest). Original bytes unchanged.
* Live-repo independence: **`CONFIRMATION_INDEPENDENCE_BLOCKED`**. Clean trees can still VERIFY.

## Task C — IUT (Planner decision applied)

* F2 = {E−D, E−C}, both **co-primary**; **IUT**; no Holm(2) on F2.
* Joint claim only if **both** reject favoring E at α=0.05.
* Freeze **v2** primary/secondary aligned; v0/v1 preserved.
* R≥6 is **necessary not sufficient** (`n_eff` nonzero pairs govern min p).

## Task D — evidence boundary

`SIMULATED_LOCAL` / `SIMULATED_DOCKER_IPC` / **`PRODUCTION_ADAPTER` (real AFlow Custom, mock model)** / `REAL_MODEL` (blocked).

## Tests (JUnit)

| Suite | passed / failed / skipped |
|---|---|
| Budget P0 | 18 / 0 / 0 |
| Freeze | 15 / 0 / 0 |
| Audit | 21 / 0 / 0 |
| Stats | 11 / 0 / 0 |
| Docker/IPC | 20 / 0 / 0 |
| Historical | 119 / 0 / 0 |
| **Full** | **1091 / 0 / 2** (1093) RETCODE 0 |

## Integrity

R3 0 modified · R3 gate unchanged · v1 confirm `1771a67c…` · v0 exec freeze kept · auth 244 / $0.0363972.

## Still open / BLOCKED

1. Live-repo audit independence BLOCKED (legacy mixed-encoding doc).  
2. Exec freeze **not** approved (PROPOSED).  
3. No Planner execution authorization → HTTP stays blocked.  
4. Quota insufficient for Plan P (528 > 56 remaining).

## STOP

Awaiting Planner independent review. No formal freeze, no preregistration approval, no real model experiment.
