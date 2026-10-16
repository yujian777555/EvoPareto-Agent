# Statistical Correction Report

Denominator fixed: only **comparable mutations** (before & after present) count
for upgrade/downgrade. SEARCH_MAIN / SEARCH_ABLATION / TEST_ONLY / INITIAL
reported separately.

| Group | rounds | comparable | succeed_flag | up | down | ties | missing |
|---|---:|---:|---:|---:|---:|---:|---:|
| SEARCH_MAIN | 122 | 120 | 29 | 28 | 88 | 4 | 2 |
| SEARCH_ABLATION | 21 | 20 | 9 | 8 | 11 | 1 | 1 |
| TEST_ONLY | 6 | 4 | 3 | 3 | 1 | 0 | 2 |
| INITIAL | 6 | 0 | 0 | — | — | — | — |

All groups: comparable=144, succeed=41, up=39, down=100, ties=5.
Mean Δ = -0.0411, median Δ = -0.0117.
Rates: succeed_flag_rate=0.265,
paired_upgrade_rate=0.271,
paired_downgrade_rate=0.694.

**Evidence class: DERIVED_STATISTICS (from OFFICIAL_DATA).**
