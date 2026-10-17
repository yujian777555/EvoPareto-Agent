# Entropy & Effective Parent Count (Task 2)

**Verdict: ENTROPY_FORMULA = CORRECT · INITIAL_PARENT_NODES_EXCLUDED = TRUE**

## Definition

```python
# only children with a real father
freqs = [c / total for c in fathers.values()]
entropy_bits = -sum(p * math.log2(p) for p in freqs if p > 0)
effective_parents = 2 ** entropy_bits
```

Initial nodes (`father node = null`) are excluded from the parent distribution.

## GSM8K/graphs

| Metric | Value | Planner target |
|---|---:|---:|
| VALID_CHILDREN | **24** | 24 |
| TOP2_PARENT_SHARE | **0.6666666666666666** | ~0.6667 |
| SELECTION_ENTROPY_BITS | **2.29597512699001** | ~2.296 |
| EFFECTIVE_PARENT_COUNT | **4.910858068512094** | ~4.911 |

matches_planner_targets = **True**

parent_selection_frequency = `{"1": 1, "2": 1, "3": 3, "4": 2, "8": 9, "10": 1, "13": 7}`

## Artifacts

- `results/stage3_0_p1_r2a_r1/corrected_lineage_metrics.json`
- `results/stage3_0_p1_r2a/lineage_metrics.json` (per-variant, recomputed)
- unit tests: `tests/baseline_first/test_entropy_units.py`

AFlow official records were not modified. Earlier R2A results are preserved as
historical; this stage writes the corrected values to `stage3_0_p1_r2a_r1/`.
