# Strict Re-verification Metadata (Task C)

| Check | Enforcement |
|---|---|
| top-level run_id | must exist and equal `parentre-8aa3d61f` |
| per-record run_id | must exist and match (missing = fail) |
| top-level task_set_sha256 | must exist and match frozen |
| top-level child_graph_sha256 | must exist and match frozen |
| ledger ↔ re-verification ↔ child hashes | cross-checked |
| duplicate task IDs | independent test (not order-swap) |
| wrong task order | independent test (IDs stay unique) |

Any missing/conflicting field fails closed. No auto-fill, no manifest reset
to mask changes. 8 regression tests.
