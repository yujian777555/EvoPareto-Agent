# Phase5-R3-R5-R1 — PEEM 2D Audit

## Fix

`objective_improvement(..., spec=)` — **no hardcoded `i==2`**.  
`ObjectiveSpec.cost_index()` explicit. 5-obj legacy path preserved (`SPEC_5`).

## Verified (offline)

- cost↓ with equal success → **positive** credit
- success↑ with equal cost → positive credit
- trade-off (not unconditional dominate) → mixed gain
- PEEM sampling probability updates from credit
- all-zero-success: cheap-fail does not explode vs planner (decay+prior)

## Degeneracy note

If **all** genomes have success=0, Pareto selection prefers lower cost —
mathematically expected. **Not silently fixed.** Options: feasibility-first
constraint (needs Planner), or treat all-zero as `BLOCKED_OBJECTIVE_DEGENERACY`
signal gate. Current default remains raw Plan B.
