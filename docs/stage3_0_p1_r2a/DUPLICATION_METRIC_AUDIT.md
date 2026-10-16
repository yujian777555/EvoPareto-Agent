# Duplication Metric Audit (Task C)

**Evidence class:** DERIVED_STATISTICS

## Prior definition (incorrect)

R2 counted "modification strings appearing more than once **within a Variant**".
That is not "number of illegal retry attempts".

## Corrected metrics

| Metric | Value |
|---|---:|
| duplicate_string_groups (exact) | 20 |
| duplicate_extra_occurrences | 29 |
| same_parent_repeats | 28 |
| cross_parent_repeats | 1 |
| cross_run_repeats | 7 |
| normalized_text_groups | 20 |
| normalized_text_repeats | 29 |

Per-group records (modification, benchmark, variant, round_ids, father_ids,
before/after scores) are in `results/stage3_0_p1_r2a/duplicate_groups.json`.

## Interpretation

AFlow check_modification dedups exact strings within a father node's local experience. cross_parent_repeats may be by-design (independent lineages), not proven bug. same_parent_repeats within one father would indicate local dedup weakness.

**Do not label cross-parent repeats as a Bug without proof.** AFlow's
`check_modification` is local to a father node's experience; independent lineages may
legitimately reach similar edits.

## Structural diversity layers (Task C2)

| Layer | Status | Value |
|---|---|---|
| RAW_TEXT_DIVERSITY | computed (SHA-256) | 146 unique / 155 |
| NORMALIZED_AST_DIVERSITY | computed | 146 unique |
| OPERATOR_COMPOSITION_DIVERSITY | computed | 9 unique |
| LINEAGE_DIVERSITY | see lineage_metrics.json | — |
| BEHAVIORAL_DIVERSITY | **NOT_AVAILABLE** | no comparable exec traces |

Caveat (Task C2): **AST difference ≠ capability difference.** Only structural text
diversity is established. Identity uses SHA-256 (Task C3); builtin `hash()` is not used.
