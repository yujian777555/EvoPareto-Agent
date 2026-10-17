# Multiprocess Adversarial Tests (Task D)

Real OS processes (not threads), each with its own `AuthorizationRecord`
instance and its own working SQLite file.

| Test | Expected | Status |
|---|---|---|
| 6 processes x 5 attempts, cap 4 | granted <= 4 | PASS |
| record counters survive | no lost updates | PASS |
| different DB paths share one budget | total <= cap | PASS |
| unknown billing blocks later processes | all refused | PASS |
| restart consistency | counters equal | PASS |
| missing/corrupt record | fail-closed | PASS |
| duplicate physical request | Reject | PASS |

Old implementation (thread-only lock + per-DB `BEGIN IMMEDIATE`) is reproduced
as the failure mode the cross-process lock now prevents.
