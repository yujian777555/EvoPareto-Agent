# Succeed Flag vs Score Delta Discrepancy (Task A3)

**Evidence class:** DERIVED_STATISTICS
**n_discrepancies = 2**
**causes = {"FLOAT_EPSILON": 2}**

## Identity check against Planner audit

Planner independently audited `results/stage3_0_p1_r2/trace_analysis.json` and reported:

| metric | Planner audit | R2A SEARCH_MAIN+ABLATION | R2A ALL (adds TEST_ONLY) |
|---|---:|---:|---:|
| comparable mutations | 140 | 140 | 144 |
| score upgrades | 36 | 36 | 39 |
| score downgrades | 99 | 99 | 100 |
| score ties | 5 | 5 | 5 |
| succeed=True | 38 | 38 | 41 |

**These match exactly.** The Planner figure is the SEARCH-only view. R2A `ALL`
adds TEST_ONLY (4 comparable, 3 up, 1 down, 3 succeed). Official records were **not**
modified to force agreement.

## succeed=38 vs upgrades=36 within SEARCH

Two records have `succeed=True` but `|delta| <= 1e-9` (floating-point epsilon):

| benchmark | variant | round | experience_file | father | before | after | succeed_flag | computed_delta | classification |
|---|---|---:|---|---:|---:|---:|---|---:|---|
| DROP | graphs | 13 | `DROP/graphs/round_13/experience.json` | 2 | 0.7403921568627451 | 0.7403921568627452 | True | 1.1102230246251565e-16 | SUCCEED_TRUE_BUT_NOT_UPGRADE (FLOAT_EPSILON) |
| GSM8K | ablation_graphs | 17 | `GSM8K/ablation_graphs/round_17/experience.json` | 9 | 0.8779999999999999 | 0.8780000000000001 | True | 2.220446049250313e-16 | SUCCEED_TRUE_BUT_NOT_UPGRADE (FLOAT_EPSILON) |

### Cause

AFlow computes `succeed = after > before` in raw float arithmetic, so a 1-ULP
difference (`1.11e-16`, `2.22e-16`) is a "success". R2A uses `TOL = 1e-9` and calls
these ties. **This is a comparison-tolerance difference only — no data corruption.**
Raw JSON types are floats (not strings) in both cases.

### Rule going forward

Report `succeed_flag_rate` and `paired_upgrade_rate` **separately**. Never equate them.
