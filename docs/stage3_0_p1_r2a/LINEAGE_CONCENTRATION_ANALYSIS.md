# Lineage Concentration Analysis (Task D, entropy corrected R1)

**Evidence class:** DERIVED_STATISTICS
**Focus:** GSM8K main search; other benchmarks in `lineage_metrics.json`.

## Unit and denominator (Task 1 fix)

Two corrections vs the first R2A pass:

1. **Initial nodes excluded.** Rounds with `father node = null` (the initial
   workflow) are not parent selections and are not counted as a parent category.
   `n_children_with_father = 24`,
   `n_initial_no_father = 1`.
2. **Entropy unit is bits (log2).** Effective parent count uses `2 ** H_bits`.
   The previous pass mixed natural-log entropy with a base-2 effective count.

## Observed concentration (GSM8K/graphs)

parent_selection_frequency = `{"1": 1, "2": 1, "3": 3, "4": 2, "8": 9, "10": 1, "13": 7}`

| Metric | Value |
|---|---:|
| n_children_with_father | 24 |
| selection_entropy | 2.29597512699001 bits |
| effective_parent_count | 4.910858068512094 |
| max_father_share | 0.375 |
| top2_father_share | 0.6666666666666666 |

Top-2 fathers produce 16/24 children (~66.7%). **Concentration is real.**

## What this does NOT establish

`PREMATURE_CONVERGENCE_CAUSALLY_ESTABLISHED = **False**`

Task D2: theoretical selection probability of each observed child
= **SELECTION_PROBABILITY_NOT_RECONSTRUCTABLE**.

AFlow `select_round` uses `lambda*uniform + (1-lambda)*softmax(alpha*score)` over
top-k father rounds. The official archive does **not** store the full per-round
candidate set nor per-run (k, alpha, lambda).

## Task D3: plateau competing explanations

[
  "TASK_SCORE_NEAR_CEILING",
  "CANDIDATE_GENERATION_QUALITY_INSUFFICIENT",
  "HIGH_SCORE_PARENT_OVERCONCENTRATION",
  "EVALUATION_NOISE",
  "SMALL_TASK_SAMPLE",
  "SEARCH_BUDGET_EXHAUSTED",
  "DUPLICATE_OR_INVALID_MUTATIONS",
  "LOCAL_SEARCH_SPACE_SATURATION"
]

Status: **PLATEAU_CAUSE_NOT_ISOLATED**.

## Task D4: counterfactual boundary

Untried parent-mutation combinations have NO observed reward. Claims that 'diversity search would yield higher performance' are NOT_SUPPORTED by historical logs.

### Verdict

- Concentration: **supported by data** (top2 ~66.7%, N_eff ~4.91 of 7 fathers)
- Harmful premature convergence: **NOT causally established**
- "Diversity search would improve performance": **NOT_SUPPORTED by this archive**
