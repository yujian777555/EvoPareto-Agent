# Lineage Concentration Analysis (Task D)

**Evidence class:** DERIVED_STATISTICS
**Focus:** GSM8K main search; other benchmarks checked in `lineage_metrics.json`.

## Observed concentration (GSM8K/graphs)

parent_selection_frequency = `{"None": 1, "1": 1, "2": 1, "3": 3, "4": 2, "8": 9, "10": 1, "13": 7}`

| Metric | Value |
|---|---:|
| n_children | 25 |
| selection_entropy | 1.6957348862067052 bits |
| effective_parent_count | 3.239418554951364 (of unique fathers) |
| max_father_share | 0.36 |
| top2_father_share | 0.64 |

Two fathers account for 16/25 children. **Concentration is real.**

## What this does NOT establish

`PREMATURE_CONVERGENCE_CAUSALLY_ESTABLISHED = **False**`

Task D2: theoretical selection probability of each observed child
= **SELECTION_PROBABILITY_NOT_RECONSTRUCTABLE**.

AFlow `select_round` uses `λ·uniform + (1-λ)·softmax(α·score)` over top-k father
rounds. The official archive does **not** store the full per-round candidate set nor
per-run (k, α, λ), so we cannot reconstruct the probability that produced each child.

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

Status: **PLATEAU_CAUSE_NOT_ISOLATED**. A best-so-far curve alone cannot separate
score ceiling, candidate quality, parent over-concentration, evaluation noise, small
task sample, budget exhaustion, duplicate/invalid mutations, or local saturation.

## Task D4: counterfactual boundary

Untried parent-mutation combinations have NO observed reward. Claims that 'diversity search would yield higher performance' are NOT_SUPPORTED by historical logs.

Historical logs only show **actually selected** parent–mutation pairs. Rewards of
untried combinations are **NOT_OBSERVABLE** and must never be filled in.

### Verdict

- Concentration: **supported by data**
- Harmful premature convergence: **NOT causally established**
- "Diversity search would improve performance": **NOT_SUPPORTED by this archive**
