# Live Snapshot Schema Fix (Task A)

## P0

`AuthBudgetLedger.snapshot()` returned a nested `consumed` dict while the
production live script read `snap["tokens_in"]` / `snap["physical_attempts"]`.
Post-settlement summarisation raised `KeyError`, so a real run could fail at
report time after a successful request.

## Contract (schema_version = "r2.1")

| Field | Meaning |
|---|---|
| `physical_attempts` | lifetime physical HTTP attempts (trusted record) |
| `actual_tokens_in` / `actual_tokens_out` | provider usage after settlement |
| `reserved_tokens_in` / `reserved_tokens_out` | outstanding pre-send token reservations |
| `outstanding_reserved_cost_usd` | $ reserved but not yet settled |
| `spent_cost_usd` | settled cost estimate (unknown billing counts the reservation) |
| `blocked` / `block_reason` | persistent fail-closed flag |
| `remaining_physical` | max_physical - physical_attempts |

Reserved and actual are **separate fields**; they are never conflated.

## Verification

`tests/baseline_first/test_l3r21_production_e2e.py` drives the **real**
`LiveClient` against a local Mock HTTP server and asserts the summarised
artifacts reflect settled amounts after settlement — not just a unit call to
`snapshot()`. The `KeyError` above is reproduced by the old field names and
fixed by the new contract.
