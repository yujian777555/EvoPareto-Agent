# Planner Handoff — Level 3-R2

## Closed

1. **Budget persistence P0** — trusted `AuthorizationRecord` (checksummed,
   explicit-create-only) plus rehydrating working DB. DB delete / path change /
   run-id rotation / restart cannot restore quota; missing or corrupt record
   fails closed.
2. **Unified HTTP budget entry** — the live production script now uses
   `UnifiedBudgetGate` on the persistent authorization; no parallel budget
   implementation remains.
3. **Atomic reservation & settlement** — strict RESERVED -> SETTLED_ACTUAL /
   SETTLED_UNKNOWN_BLOCKED state machine; duplicate IDs and double settlement
   rejected; outstanding reservations counted toward the cost cap.
4. **Bundle reliability** — prompt_contract kind fixed; compile vs load
   distinguished; `INSTRUCTION` binding enforced; graph bytes untouched.

## Guarantees and their boundary

Protection targets normal-experiment faults (mistaken deletion, restart,
directory switch, double init). It is **not** a defence against an attacker
with full filesystem control who can rewrite the integrity seal.

## Resource use

NEW_REAL_HTTP_REQUESTS = 0 · REAL_API_COST_ADDED = $0

## Next

Await Planner authorization for the next live calibration slice or the $5
pilot. Executor will not send real API requests without explicit approval.
