# Phase5-R3-R5 — API Budget Audit

## Leak at 9ebddc6

`_reserve` added `reserved_cost` but `_settle` never subtracted it →
`reserved_cost_usd=0.000967` after all requests done.

## Fix

Ticket map `_pending_cost[ticket]=est_cost`; `_settle` pops ticket and
subtracts. `assert_clean_shutdown()` for tests.

## Physical HTTP

`post_json` increments `bump_physical_http()` before each curl/urllib send.
402/401/403 abort the retry ladder. Persistent ledger (`ledger_path`) restores
budget across processes.

## Tests

`tests/test_r3r5_objectives_budget.py` — reserve release on success/fail/402,
concurrency, physical counter, persistent ledger.
