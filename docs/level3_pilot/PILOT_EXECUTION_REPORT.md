# Level 3 Real Pilot Execution Report

**Run id:** `pilot-e500d1fa27`
**Authorization:** EXPLICIT_CREATE (shared cumulative, $5 hard cap)

## Preflight gates (zero-cost)

| Gate | Status |
|---|---|
| MOCK_PREFLIGHT | PASS (47 mock/budget tests) |
| CRASH_RECOVERY_GATE | PASS |
| GLOBAL_BUDGET_GATE | PASS |
| PRODUCTION_E2E_GATE | PASS |
| FROZEN_RESULTS | 367 files, unchanged |

## Real execution

| Metric | Value |
|---|---|
| REAL_MODEL | deepseek-flash |
| REAL_HTTP_REQUESTS | **2** / 300 |
| REAL_INPUT_TOKENS | 151 |
| REAL_OUTPUT_TOKENS | 640 |
| REAL_API_COST_USD | **0.0008979** / 5.00 |
| BUDGET_REMAINING_USD | 4.9991021 |
| STOP_REASON | **RESPONSE_TRUNCATED** |

## Stage results (real DeepSeek)

### Stage 1 — GSM8K train math

- status: **OK**
- model returned: deepseek-flash · finish_reason: stop
- predicted: `10` · gold (host only): `10`
- **correct: True** — real model solved the train problem

### Stage 2 — Optimizer XML mutation

- status: **FAILED**
- error: RuntimeError: RESPONSE_TRUNCATED
- cause: `finish_reason=length` — the 500-token output cap truncated the XML

Per the stop rules (incomplete response), the run halted here and consumed no
further quota. No Mock fallback was used.

## Budget gate evidence

Every request reserved worst-case cost before send, settled after usage was
read, and the cumulative totals stayed far below the $5 cap. The authorization
record is shared across runs and cannot be reset by run-id or DB-path changes.

## Reproducibility

`scripts/level3_pilot/run_pilot.py` + `results/level3_pilot/pilot_ledger_<run_id>.json`.
