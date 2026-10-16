# Duplication Metric Audit

| Metric | Value |
|---|---:|
| duplicate_string_groups | 20 |
| duplicate_extra_occurrences | 29 |
| same_parent_repeats | 28 |
| cross_parent_repeats | 1 |

Most repeats are **same-parent** (local `check_modification` allows retries
within a father's experience or successive identical edits). Cross-parent
repeats are rare (1) and may be **by design** (local dedup), not a bug.
