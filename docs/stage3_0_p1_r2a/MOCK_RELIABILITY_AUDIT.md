# Mock Reliability Audit (Task H)

**Evidence class:** MOCK_TEST
**verdict = MOCK_RELIABILITY_PASS**

| Check | Value |
|---|---|
| fresh run_id | `d37d06202700` |
| exit_code | 0 |
| official_search_loop | PASS |
| trace run_id | `d37d06202700` |
| events verified (modifications + selections present) | True |
| forced-failure exit code | 1 |
| failure produces non-zero exit | True |
| old result cannot impersonate new run | True |

## Fixes vs R1

1. `aflow_e2e_mock.py` now accepts `--run-id` and writes it into
   `results/stage3_0_p1_r1/mock_execution_trace.json`.
2. `main()` returns **1** when `official_search_loop != "PASS"` (was always 0).
3. Negative run replaces `MockLLM` with a raising class; the process exits non-zero,
   proving failure is not a silent PASS.
4. Verification requires actual search events (modifications + selections), not a
   hardcoded `"PASS"` string in a committed JSON.

**Mock ≠ real model success.** This audit only covers the offline search path.
