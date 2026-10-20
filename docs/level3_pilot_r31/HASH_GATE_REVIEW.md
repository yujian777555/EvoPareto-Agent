# Hash Gate Review (Task A+B)

## Problem

`EXPECTED_TASK_HASH = "ddf055537d4618c8"` was a truncated prefix and the
comparison only checked the declared hash in the JSON against recomputed —
the expected constant was unused.

## Fix

1. `EXPECTED_TASK_HASH` fixed to the full frozen value:
   `ddf055537d4618c86d736d4f0ed98fd4b23efec21f9e0ffe65a2c8ee022a6219`
2. `verify_taskset()` extracted as a pure function:
   - field completeness check FIRST
   - task ID uniqueness and ordering
   - recomputed hash == declared hash
   - declared hash == expected hash (tamper-proof even if attacker updates declared)
3. Any failure → exit 3 before any HTTP call.

## Regression tests (11)

| Test | Expected |
|---|---|
| valid frozen taskset | pass |
| tampered question | TASK_SET_HASH_MISMATCH |
| tampered answer | TASK_SET_HASH_MISMATCH |
| replace task, keep old declared hash | TASK_SET_HASH_MISMATCH |
| change task AND declared hash | TASK_SET_HASH_UNEXPECTED |
| duplicate task ID | TASK_ID_DUPLICATE |
| wrong order | TASK_ORDER_MISMATCH |
| missing declared hash | DECLARED_HASH_MISSING |
| missing expected hash | EXPECTED_HASH_MISSING |
| missing field | TASK_FIELD_MISSING |
| (audit reproducibility) | 0/35 matches reproduced |
