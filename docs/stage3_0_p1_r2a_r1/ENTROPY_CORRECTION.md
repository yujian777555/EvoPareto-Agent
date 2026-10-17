# Entropy & Effective Parent Count Correction (Task 1)

**Evidence class:** DERIVED_STATISTICS
**Verdict: CORRECTED**

## Bugs fixed in `scripts/baseline_first/r2a_full_analysis.py::task_d`

1. **Initial nodes were counted as parents.** Rounds with `father node = null`
   (the initial workflow) are not parent selections. They polluted the frequency
   distribution as a fake parent named `"None"`.
2. **Entropy unit was wrong.** The code used `math.log` (nats) but labelled the
   result `selection_entropy_bits`, and computed effective count as
   `2 ** entropy_nats` — mixing base-2 with natural-log.

## Correct definition

- Denominator = children **with a real father**
- `H_bits = -sum(p * log2(p))` over parent frequencies
- `effective_parent_count = 2 ** H_bits`

## GSM8K/graphs (verified)

| Metric | R2A (wrong) | R2A-R1 (correct) | Planner target |
|---|---:|---:|---:|
| children counted | 25 (incl. 1 initial) | **24** | 24 |
| top2 father share | 0.64 | **0.6667** | ~0.667 |
| selection entropy | 1.696 nats | **2.296 bits** | ~2.296 |
| effective parent count | 3.24 (mixed units) | **4.91** | ~4.91 |

parent_selection_frequency (after fix) = `{"1": 1, "2": 1, "3": 3, "4": 2, "8": 9, "10": 1, "13": 7}`

## Reproducibility

- Unit test: `tests/baseline_first/test_entropy_units.py` (4 tests)
- Checks both the pure-math identity and that `lineage_metrics.json` matches
- `2 ** H_bits == exp(H_nats)` verified as the same effective number

Official AFlow records were **not** modified.
