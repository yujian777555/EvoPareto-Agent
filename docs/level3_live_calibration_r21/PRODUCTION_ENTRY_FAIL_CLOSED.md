# Production Entry Fail-Closed & Legacy Migration (Task B)

## P0

`run_live_calibration.py` auto-called `AuthorizationRecord.create()` when the
record was missing — silently minting fresh quota.

## Fix

`open_production_authorization()` is the only production entry:

1. `AuthorizationRecord.open_existing()` — verify integrity, identity, caps
2. restore cumulative requests / cost / actual tokens / reserved tokens / blocked
3. missing or corrupt record -> **fail-closed** (exit 3, no HTTP)
4. new Run ID / new DB path / restart cannot recreate quota

New quota requires the **explicit** `AuthorizationRecord.create()` procedure,
which refuses to run when a record already exists.

## Legacy Level 3 migration (explicit, idempotent)

`AuthorizationRecord.migrate_legacy_level3(ledger_json)`:

- verifies source SHA-256
- checks the Planner baseline: **2 requests, 162 in, 454 out, $0.0005934**
- refuses any other baseline
- records the source SHA + migrated physical request IDs
- second call is a no-op (idempotent)

Distinguishes three flows: `open_existing` (restore), `migrate_legacy_level3`
(one-shot import), `create` (explicit new authorization).

Verified by `tests/baseline_first/test_l3r21_multiprocess.py` against the real
`results/level3_live_calibration/request_ledger.json`.
