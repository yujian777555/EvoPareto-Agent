# R2-R2 — PEEM Fidelity (2D)

## Root cause

`dominates_mixed` used `i == 2` as cost. For `candidate_2obj`, cost index = 1.

## Fix

`ObjectiveSpec`-driven dominance:

- `dominates_mixed(a, b, spec=None)` → SPEC_2 when dim=2, SPEC_5 otherwise
- `ParetoContributionEstimator.score_one(..., spec=)`
- `compute_credit(..., spec=)` chain from `MemoryEvolutionLoop`

## Golden cases (through real PEEM call chain)

| case | expected | result |
|------|----------|--------|
| A≻B, A≻C, A∥D | true / true / incomparable | ✅ |
| cost↓ | positive improvement | ✅ |
| cost↑ | negative improvement | ✅ |
| trade-off | not unconditional dominate | ✅ |

Legacy 5-obj regression: `test_peem_credit_uses_spec` + full suite green.
