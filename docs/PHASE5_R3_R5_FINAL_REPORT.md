# Phase5-R3-R5 — Final Report

## 1. Git

Commit this SHA · origin/main synced · working tree clean.

## 2–4. API budget

| check | result |
|-------|--------|
| reserved_cost leak | **FIXED** (ticket settle) |
| after live smoke | `reserved_cost_usd=0`, `reserved_calls=0` |
| physical HTTP count | `bump_physical_http` per curl/urllib send |
| persistent ledger | restores across processes |
| 402 fail-fast | `BillingBlocked`, no retry |

## 5–6. Objectives

**Plan A (5-obj repaired):** success-conditioned efficiency (fail×0.3),
robustness = μ−0.5σ², autonomy = 1−fallback/help rates.  
**Plan B (2-obj):** max success, min API cost; steps/tokens diagnostics.

Construction cases stored in
`results/phase5_r3_r5/objective_counterexamples/construction.json`.

## 7. 2D NSGA-III

5 reference directions at H=4; valid simplex. **NSGA-II baseline recommended**
if Plan B adopted.

## 8–9. PEEM / PPEC

PEEM updates sampling from fitness credit (offline proof). PPEC changes
reference directions + selection under different preferences. All-zero-success
collapse not observed.

## 10. Four-method prereg

`PHASE5_R3_R5_FOUR_METHOD_PREREG.md` — arms A–D, H=30 valid_train, shared
budgets, attribution table. **Pilot 2 not run.**

## 11. Offline tests

Host pytest **all green** (budget settlement, physical count, 2D dirs,
candidate versions, no-proxy native path).

## 12. Live smoke

2× `deepseek-flash` OK · tokens 9/1 · cost $2.2e-6 · reserved_cost 0 · cap $0.10.

## 13. Recommended objective

**Plan B: Performance + Cost** (formal). Plan A secondary after robustness
protocol. Freeze required before Pilot 2.

## 14. Pilot readiness

Engineering yes; scientific comparison awaits Planner objective freeze.

## 15. Final status

**`ACCEPTED_OBJECTIVE_DESIGN_READY`**
