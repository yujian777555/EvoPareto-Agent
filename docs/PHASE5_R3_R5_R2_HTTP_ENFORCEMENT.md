# Phase5-R3-R5-R2 — HTTP Enforcement

## Fail-closed

- strict mode + no gate → `GateRequired` (0 sends)
- BudgetDB missing/corrupt → exception before send
- BudgetExceeded → no send, no curl→urllib fallback
- 402/401/403 → no retry ladder

## Ticket lifecycle

```text
acquire_ticket (BEGIN IMMEDIATE, uuid)
    → physical send
    → settle(ticket) exactly once
```

- double settle → `RuntimeError`
- unknown ticket → `UnknownTicket`
- crash: open tickets counted as spent attempts (conservative)

## Cap proof

`physical_attempts + open_tickets < max_physical` enforced atomically.
Cross-process via SQLite WAL + busy_timeout. Caps never silently raised.

## Offline tests

`tests/test_r5r2_fidelity.py` + `test_r5r1_2d_fidelity.py`: gate block,
persist, double-settle, crash recovery, strict no-gate.
