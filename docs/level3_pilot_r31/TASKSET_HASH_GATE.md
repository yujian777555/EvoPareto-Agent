# Task-Set Hash Gate (Task B)

## Problem

`EXPECTED_TASK_HASH` in `run_paired_35.py` was defined but **never validated**.
The program only checked task count and copied the declared hash into results.

## Fix

Before any real call:
1. Recompute SHA-256 from actual `(task_id, question, gold_answer)` tuples
   using canonical sorted-JSON serialization.
2. Compare against the declared `task_set_sha256` in the frozen file.
3. Verify task IDs are unique and ordered.
4. Any mismatch → fail-closed (exit 3).

Tamper detection: modifying a question, swapping an answer, replacing a task
while keeping the old hash, or reordering all trigger `TASK_SET_HASH_MISMATCH`.

The manifest is never auto-created or reset by the normal experiment entry.
