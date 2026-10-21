# R4-R6 Budget Bypass / Remaining-Quota Audit

**P0 closed for the listed bypass classes.** Real API this round: **0**. Auth **not** modified.

## Fixed contract (code-versioned `R4-BUDGET-POLICY-v1`)

`requests_formula=240+240*R`, `base_requests=240`, `per_r_requests=240`, `safety_margin=0.10`, tokens in/out (150,400)/(150,800), `usd/req=0.003`.

Config numbers are checked **against POLICY**, not merely for self-consistency. `config_sha256` is never budget evidence.

## Bypass tests (all must reject after rehash)

| Mutation | Result |
|---|---|
| lower `base_requests` / `per_r_requests` / margin / tokens / usd / formula | `BUDGET_POLICY_*` |
| negative / bool / string numbers | `BUDGET_POLICY_TYPE/MISMATCH` |
| NaN / inf | `BUDGET_POLICY_NOT_FINITE` / `BudgetError` |
| missing budget fields | `BUDGET_POLICY_MISSING` |
| `planned_r_values` ≠ `seeds.r_values` | `BUDGET_PLANNED_R_NEQ_SEEDS` |
| planned R ≠ `plan_seeds` keys | `BUDGET_PLANNED_R_NEQ_PLAN_SEEDS` |
| rehash only | still rejected |

## Remaining-quota semantics

`remaining = max − consumed` for requests, tokens in/out, USD.  
Feasibility compares **demand vs remaining**, not vs max. Missing `remaining_*` → `BUDGET_REMAINING_MISSING` (no fallback to max).

Live snapshot (read-only): remaining requests **56**, remaining USD ≈ 4.96, remaining tokens_out ≈ 172395.

| R | demand (incl. 10%) | vs remaining 56 | verdict |
|---:|---:|---|---|
| 1 | 528 | exceed | REJECT |
| 6 | 1848 | exceed | REJECT |
| 10 | 2904 | exceed | REJECT |

## Execution authorization ≠ budget pass

`verify_execution_allowed()`: PROPOSED status → `EXEC_STATUS_BLOCKS_HTTP`; no Planner flag → `EXEC_NOT_AUTHORIZED_BY_PLANNER`; budget still re-checked. Model-call count in gate paths: **0** (no HTTP imports).

## Unresolved

Formal freeze still **PROPOSED**. Any real run needs new authorization (requests + tokens) and Planner execution approval.
