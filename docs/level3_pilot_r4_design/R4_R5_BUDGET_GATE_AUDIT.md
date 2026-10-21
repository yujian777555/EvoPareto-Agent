# R4-R5 Budget Gate Audit

**Evidence class:** OFFLINE_REPRODUCIBLE  
**Baseline:** `ed1623a7fae56d6293fb05a71258b5d3747af7c5`  
**Real API requests:** **0**  
**Authorization:** read-only snapshot; **not modified**.

---

## 1. Defect

`verify_exec_freeze()` only checked that `requests_formula` existed. R=6 / R=10 plans exceeded real caps but still returned `""`.

## 2. Fix

| Piece | Location |
|---|---|
| Pure arithmetic | `compute_budget_requirements(R, …)` → `BudgetRequirements` |
| Cap comparison | `verify_budget_feasibility(req, auth)` |
| Structure/hash only | `verify_exec_config_structure` |
| Full gate | `verify_exec_freeze(config, auth=…, require_budget=True)` |
| Auth load | `load_auth_snapshot` — **read-only**, never creates/resets |

Margin uses exact `Fraction` so `ceil(1680×1.1)=1848` (not float 1849).

## 3. Frozen budget facts (authority snapshot)

| Cap | Value |
|---|---:|
| max requests | 300 |
| max tokens in | 2,000,000 |
| max tokens out | 200,000 |
| max USD | 5.00 |

Per-request worst: in 400, out 800, $0.003. Formula `240+240R`, margin 10%.

## 4. Computed demand (incl. 10% margin)

| R | base req | +margin | tokens_out (margin) | USD (margin) | Gate |
|---:|---:|---:|---:|---:|---|
| 1 | 480 | **528** | 422,400 | $1.584 | **REJECT** `BUDGET_REQUESTS_EXCEEDED:need=528,max=300` |
| 6 | 1,680 | **1,848** | 1,478,400 | $5.544 | **REJECT** `BUDGET_REQUESTS_EXCEEDED:need=1848,max=300` |
| 10 | 2,640 | **2,904** | 2,323,200 | $8.712 | **REJECT** `BUDGET_REQUESTS_EXCEEDED:need=2904,max=300` |

If request cap were large enough, token-out and USD would also fail for R=6/10 (covered by tests).

## 5. Fail-closed properties

| Case | Result |
|---|---|
| Config hash OK, budget short | **REJECT** (structure ≠ budget) |
| Missing / corrupt auth | `BUDGET_AUTH_UNAVAILABLE:…` |
| Blocked auth | `BUDGET_AUTH_BLOCKED` |
| Bad numeric fields | `BUDGET_FIELDS_INVALID` / `BudgetError` |
| Overflow | `BudgetError` |
| Auth created/reset in verify path | **never** |

## 6. Files

* `src/research/r4_exec_freeze.py` (v1 semantics)
* `docs/level3_pilot_r4_design/execution_freeze_v1_proposed.json` (new; **v0 preserved**)
* `tests/baseline_first/test_r4_exec_freeze.py` (15 tests)

## 7. Verdict

**Acceptance met:** R=6 and R=10 rejected by budget gate **before any model HTTP**.  
Formal execution freeze remains **PROPOSED / not approved**.
