# Production Mock HTTP End-to-End (Task E)

Drives the **real** `LiveClient` from `run_live_calibration.py` through:

```
LiveClient -> UnifiedBudgetGate -> AuthorizationRecord
           -> Mock HTTP Transport -> Usage Parsing -> Settlement
           -> Snapshot -> Result Artifacts
```

| Scenario | Result |
|---|---|
| HTTP 200 valid | settled, artifacts written from snapshot |
| HTTP 429 | recorded with status 429 |
| HTTP 500 | fail-closed + persistent block |
| network timeout | blocked / attempt recorded |
| invalid JSON | fail-closed |
| empty response | rejected |
| missing usage | fail-closed |
| token over cap | rejected BEFORE send (0 attempts) |
| budget exhausted | second request refused |
| authorization missing | fail-closed |
| settlement failure | recorded |
| optimizer + child phases | shared one authorization |

Physical request counts, ledger rows, tokens, cost and state are asserted
consistent. Transport is local Mock HTTP only — no real DeepSeek.
