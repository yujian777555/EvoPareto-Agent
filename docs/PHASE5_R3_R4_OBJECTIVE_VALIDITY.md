# Phase5-R3-R4 — Objective Validity Audit

**Formulas unchanged** (diagnostics only). See
`results/native_alfworld/objective_diagnostics/objective_validity.json`.

| Objective | Measurement | Valid? | Issues |
|-----------|-------------|--------|--------|
| Performance | env `won` | **YES** | unchanged |
| Efficiency | 1/(1+steps/H+tokens/2000) | **NO** | **quick-fail beats success** (0.94 > 0.54) |
| Cost | API $ saturating | PARTIAL | micro range tiny (min≈0.001) |
| Robustness | perf×(1−stall) | **NO** | collapses to 0 when all fail; redundant with perf |
| Autonomy | early-budget/stall penalties | **NO** | behavioral proxy only |

## Counterexample (efficiency)

| episode | eff_v1 |
|---------|--------|
| fail 1 step | **0.943** |
| fail 10 steps | 0.588 |
| success 12 steps | 0.541 |

Quick-fail is rewarded more than success → Goodhart risk.

## Candidates (NOT approved)

- **Efficiency-conditional:** `eff` if success else `0.35*eff`
- **Robustness:** multi-instance success stability / seed variance
- **Autonomy:** `1 - fallback_rate - 0.5*external_help_rate`

## Plans

- **A:** keep 5 objectives + measurement protocol upgrades (success-conditioned
  efficiency, independent robustness, behavioral autonomy)
- **B:** reduce/reorganize axes (requires Planner approval + PPEC vector update)

**Recommendation to Planner:** do not put efficiency/robustness/autonomy in
main tables until protocol A is approved and re-measured.
