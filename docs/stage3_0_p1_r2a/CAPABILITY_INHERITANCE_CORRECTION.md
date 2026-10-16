# Capability Inheritance Correction (Task B)

**Evidence class:** DERIVED_STATISTICS
**Verdict: INHERITANCE_PARTIALLY_SUPPORTED**
**Behavioral inheritance: BEHAVIORAL_INHERITANCE_NOT_ESTABLISHED**

## Correct lineage model

Previous R2 code used `succ_fathers = {r['father'] for r in succeeds}` then counted
children of those fathers. That confuses the **successful child** with the **father of
the successful mutation**.

Correct definition:

```
Parent P  --successful mutation-->  Child C (round r)
Child C   --later selected as father-->  Grandchildren G
```

- **successful_child_reselection_rate** = share of success children whose round id
  later appears as `father node` of another round in the same (benchmark, variant)
- **successful_child_offspring_count** = number of direct descendants of that child
- **descendant_score_retention** = share of direct offspring with `after >= child.after`
- **lineage_survival_depth** = father-chain length
- **structural_component_retention** = share of success children with ≥1 offspring
  sharing identical `graph.py` SHA-256

## Numbers (SEARCH groups only)

| Metric | success children | fail children |
|---|---:|---:|
| n | 38 | 102 |
| reselection rate | **0.763** | 0.098 |
| mean offspring | **2.42** | 0.22 |
| median offspring | 2.0 | 0.0 |
| lineage depth mean | 3.5 | 4.431372549019608 |
| descendant score retention | 0.32318007662835246 | 0.38333333333333336 |
| structural retention | 0.0 | 0.0 |

## Controls (Task B3)

Matched by creation-round quartile (controls remaining selection opportunities):

[
  {
    "creation_round_quartile": 0,
    "n_success": 14,
    "n_fail": 13,
    "mean_offspring_success": 3.0,
    "mean_offspring_fail": 0.7692307692307693,
    "reselection_success": 1.0,
    "reselection_fail": 0.3076923076923077
  },
  {
    "creation_round_quartile": 1,
    "n_success": 10,
    "n_fail": 24,
    "mean_offspring_success": 3.4,
    "mean_offspring_fail": 0.16666666666666666,
    "reselection_success": 0.9,
    "reselection_fail": 0.125
  },
  {
    "creation_round_quartile": 2,
    "n_success": 7,
    "n_fail": 28,
    "mean_offspring_success": 2.0,
    "mean_offspring_fail": 0.2857142857142857,
    "reselection_success": 0.5714285714285714,
    "reselection_fail": 0.10714285714285714
  },
  {
    "creation_round_quartile": 3,
    "n_success": 7,
    "n_fail": 37,
    "mean_offspring_success": 0.2857142857142857,
    "mean_offspring_fail": 0.0,
    "reselection_success": 0.2857142857142857,
    "reselection_fail": 0.0
  }
]

Early children have more remaining selection opportunities; matched quartiles reduce but do not eliminate survivorship. Observational only.

## Research conclusion

- **INHERITANCE_SUPPORTED** — no
- **INHERITANCE_PARTIALLY_SUPPORTED** — yes, for **reselection / structural**
- **Behavioral capability retention — NOT_ESTABLISHED**

Code similarity and parent-child links are **not** sufficient evidence that a
capability is retained on new tasks. Official archive has no comparable per-sample
execution traces to test behavioral retention.

**Verdict: INHERITANCE_PARTIALLY_SUPPORTED**
