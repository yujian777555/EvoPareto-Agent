# R2-R1 — API Accounting

## Live launcher (strict)

`launch_live_experiment()`:
- requires `DEEPSEEK_API_KEY`
- opens `BudgetDB`, checks not exhausted
- installs `PhysicalBudgetGate(strict=True)`
- fails closed on any bootstrap error

## Ticket + usage

`acquire_ticket` → HTTP → `settle(ticket, tokens_in, tokens_out, cost)`.
Double settle rejected. Tokens accumulate in SQLite.

## Lease-safe recovery

Opening DB **does not** abandon open tickets (would free another process's
reservation). `recover_stale(older_than_seconds)` expires old in-flight tickets
conservatively (count as spent attempts).

## Tests

`test_r2r1_readiness.py` / `test_r5r2_fidelity.py`: strict no-gate, token settle,
active-ticket preservation, crash recovery via recover_stale.
