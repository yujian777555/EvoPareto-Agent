# Falsification Analysis

## What would falsify FCEOL

- H1 (failure info utility): fceol ≤ global_aos on held-out Δ across seeds.
- H2 (intervention credit): learned credit ≤ fixed failure→operator map.
- H3 (generalization): held-out Δ ≤ 0 or negative transfer dominates.
- Shuffled labels **not** worse than fceol → failure conditioning adds nothing.

## Current status

| Hypothesis | Status |
|---|---|
| H1 | **weakly supported** (Δ +0.159 vs AOS held-out; success rate mixed) |
| H2 | **weakly supported** (fceol > fixed_map on Δ) |
| H3 | **weakly supported** (heldout Δ > train Δ; single seed) |
| Shuffled control | **supports dependence on failure evidence** |

**CONDITIONAL_OPERATOR_LEARNING: preliminary benefit observed, not established.**
One seed, synthetic env, mixed success-rate metric. Do not claim a paper result.

## Negative findings preserved

- global_aos had higher held-out success_rate (0.81 vs 0.69).
- oracle control broken in this prototype (negative Δ).
- fixed_map competitive on success_rate.
