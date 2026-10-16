# Statistical Correction Report (Stage 3.0-P1-R2A)

**Evidence class:** DERIVED_STATISTICS (from OFFICIAL_DATA)
**Source:** `external/AFlow_results` (archive SHA-256 `F460F9C9218216F6FBAF553F4F215248317B7F37DD715AE146CD38199EABE5F7`)
**Script:** `scripts/baseline_first/r2a_full_analysis.py` (re-runnable)
**Tolerance:** `|delta| <= 1e-9` counted as tie. `delta = after_score - before_score`.

## Dataset grouping (Task A1)

| Group | Definition | n_rounds | comparable |
|---|---|---:|---:|
| SEARCH_MAIN | non-ablation non-test variant, round > 1 | 122 | 120 |
| SEARCH_ABLATION | variant contains `ablation`, round > 1 | 20 | 20 |
| TEST_ONLY | `*_test` held-out variant | 6 | 4 |
| INITIAL_WORKFLOW | round <= 1 (not a mutation) | 7 | 0 |

Search main / ablation / test directories are **never mixed** for mutation rates.
Cross-benchmark aggregates are labeled `ALL` and include TEST_ONLY; the Planner-facing
search-only view is `SEARCH_MAIN + SEARCH_ABLATION` only.

## Correct rates (Task A2)

Denominators:
- `succeed_flag_rate` = succeed_true / n_rounds
- `paired_upgrade_rate` = upgrades / **comparable mutations** (before AND after present)
- `paired_downgrade_rate` = downgrades / comparable mutations
- `tie_rate` = ties / comparable mutations

| Group | rounds | initial | comparable | succeed | up | down | ties | missing | succeed_flag_rate | paired_upgrade | paired_downgrade | tie_rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ALL | 155 | 7 | 144 | 41 | 39 | 100 | 5 | 11 | 0.265 | 0.271 | 0.694 | 0.035 |
| SEARCH_MAIN | 122 | 0 | 120 | 29 | 28 | 88 | 4 | 2 | 0.238 | 0.233 | 0.733 | 0.033 |
| SEARCH_ABLATION | 20 | 0 | 20 | 9 | 8 | 11 | 1 | 0 | 0.450 | 0.400 | 0.550 | 0.050 |
| TEST_ONLY | 6 | 0 | 4 | 3 | 3 | 1 | 0 | 2 | 0.500 | 0.750 | 0.250 | 0.000 |

Mean delta (ALL) = **-0.04109371107494694**, median = **-0.012521008403361289**.

## Stability (Task A4)

Independent unit = one `(benchmark, variant)` search lineage. Candidate-level deltas
inside a lineage are **not** independent samples.

- run units: **11**
- mean of unit means: **-0.0059279344300593945**
- median of unit means: **-0.0028999999999999803**

Per-benchmark rows are in `corrected_statistics.json` under `BENCH:*` / `BENCHVAR:*`.
No confidence interval is reported at candidate level; that would treat correlated
candidates as independent.

## Evidence labels

- Official before/after/succeed fields: **OFFICIAL_DATA**
- Rates, deltas, groups: **DERIVED_STATISTICS**
- Nothing here is a real-model run.
