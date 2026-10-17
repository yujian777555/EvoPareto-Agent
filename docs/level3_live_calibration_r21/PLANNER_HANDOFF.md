# Planner Handoff — Level 3-R2.1

## P0 closure

1. **Snapshot schema** — documented `r2.1` contract with separate
   `actual_tokens_*` / `reserved_tokens_*`; production summarisation no longer
   KeyErrors. E2E proves artifacts reflect settled amounts after settlement.
2. **Fail-closed entry** — `open_production_authorization()` never creates
   quota. Legacy Level 3 import is explicit, SHA-verified, baseline-checked
   (2 / 162 / 454 / $0.0005934) and idempotent.
3. **Cross-process atomicity** — OS file lock + re-read-inside-lock + atomic
   replace; multiprocess tests with separate DBs and separate record instances
   never exceed the cap and never lose counters.

## Guarantees and boundary

Targets normal-experiment faults (crash, delete, concurrent processes,
double init). Not a defence against an attacker who can rewrite the integrity
seal under full filesystem control.

## Resource use

NEW_REAL_HTTP_REQUESTS = 0 · REAL_API_COST_ADDED = $0

## Next

Await Planner authorization for the next live slice or the $5 pilot.
