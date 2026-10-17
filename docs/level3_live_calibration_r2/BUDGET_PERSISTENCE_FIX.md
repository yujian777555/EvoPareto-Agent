# Budget Persistence P0 Fix (Task A)

## Root cause

`AuthBudgetLedger._migrate_if_needed()` created a **fresh zero-consumption
budget** whenever the working SQLite DB was new. Deleting the DB (or switching
its path) silently restored full quota. A fixed `auth_id` string proved nothing.

## Design

Two layers:

| Layer | Role | Deletable? |
|---|---|---|
| `AuthorizationRecord` (checksummed JSON) | trusted cumulative consumption + caps | NO — missing/corrupt = FAIL CLOSED |
| `AuthBudgetLedger` (SQLite working DB) | per-session request state machine | YES — rehydrates from record, never from zero |

- `AuthorizationRecord.create()` is the **only** way to mint new quota.
- `open_existing()` verifies a SHA-256 integrity seal; a tampered record raises
  `AuthorizationIntegrityError` instead of re-initialising.
- Every reserve/settle atomically updates the record (write-temp + rename).

## Explicit test matrix

| Scenario | Result |
|---|---|
| consume 2, restart | remaining = 8 |
| consume 2, new Run ID | remaining = 8 (both runs counted) |
| consume 2, delete working DB | remaining = 8 (NOT 10) |
| change DB path | remaining = 8 (NOT 10) |
| delete authorization record | FAIL CLOSED (`AuthorizationMissing`) |
| corrupt record (flip counters) | FAIL CLOSED (`AuthorizationIntegrityError`) |
| create() twice | rejected (`AUTHORIZATION_ALREADY_EXISTS`) |

## Scope of the guarantee

Protects against **normal-experiment** faults: accidental deletion, restart,
directory switching, abnormal recovery, double initialisation. It does **not**
claim to defeat an attacker with full filesystem control who can rewrite every
file including the integrity seal.
