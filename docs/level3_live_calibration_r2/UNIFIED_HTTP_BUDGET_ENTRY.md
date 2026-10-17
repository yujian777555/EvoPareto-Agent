# Unified Real HTTP Budget Entry (Task B)

## Requirement

Every path that can reach DeepSeek must share one budget gate:

```
Request -> Validate -> Identify Authorization
        -> Atomic Reservation -> Physical Send
        -> Read Provider Usage -> Atomic Settlement -> Persist Evidence
```

## Implementation

`src/runtime/auth_ledger.py::UnifiedBudgetGate` is the single adapter.

`scripts/level3_live_calibration/run_live_calibration.py` (the production live
entry) was rewired off the old `BudgetDB`/`PhysicalBudgetGate` onto
`AuthorizationRecord + AuthBudgetLedger + UnifiedBudgetGate`.

Covered call sites: Optimizer mutation, GSM8K math, Docker-child Model IPC,
failure retries. There is no independent second budget implementation.

## Cost reservation inequality

```
spent_cost + outstanding_reserved_cost + new_request_reserved_cost
    <= authorized_max_cost
```

enforced inside `reserve()` with `BEGIN IMMEDIATE` on the working DB **and**
a locked update of the trusted record.
