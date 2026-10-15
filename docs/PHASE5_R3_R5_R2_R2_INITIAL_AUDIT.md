# R2-R2 — Initial Audit

**HEAD `ae89173`** = origin/main

## Blocking issues (confirmed in source)

| id | location | defect |
|----|----------|--------|
| A | `src/utils/pareto.py` `dominates_mixed` | `i == 2` hardcodes 5-obj cost index |
| B | `http_client` settle before usage parse | tokens/cost not on ticket |
| C | `recover_stale` bound all open tickets | could free live process tickets |
| D | PPEC test | no fail-able env-selection assertion |

## Fixes this phase

- `dominates_mixed(..., spec=)` + dim-based SPEC_2/SPEC_5
- `pareto_credit.score_one(..., spec=)` wired from `memory_evolution`
- HTTP: parse usage then settle tokens
- `recover_stale`: only stale ticket IDs
- PPEC: niching truncation set-difference assertion
