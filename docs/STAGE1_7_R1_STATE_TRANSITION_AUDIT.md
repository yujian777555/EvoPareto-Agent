# Stage 1.7-R1 State Transition Audit

Evidence: `results/stage1_7_r1/state_transition_tests.json`.

| Rule | Test | Result |
|---|---|---|
| Early discover+acquire satisfies LOCATE **and** ACQUIRE | `test_early_facts_satisfy_later_subgoals` | PASS |
| EXPLORE not SATISFIED after one empty visit | `test_explore_not_done_after_one_visit` | PASS |
| Failed pickup: no hold, other inventory kept | `test_failed_pickup_does_not_hold_or_clear_inventory` | PASS |
| Unconfirmed place: hold not cleared | `test_unconfirmed_place_keeps_hold` | PASS |
| Confirmed place: release + placed fact | `test_confirmed_place_releases` | PASS |
| Released ≠ still held | `test_released_not_still_held` | PASS |
| Tool located via visible `use` command | `test_tool_located_via_admissible_not_hardcode` | PASS |

## Mechanism

After each `(action, feedback, admissible)` the planner:

1. updates exploration phases (`VISITED_UNINSPECTED` / `INSPECTED_NO_TARGET` / `TARGET_FOUND`)
2. updates inventory/tool facts from **feedback phrases**
3. calls `_reconcile()` which SATISFIES any subgoal whose preconditions are
   already confirmed — no repeated actions required to advance internal state
4. never SATISFIES from unconfirmed guesses (conflicts → UNKNOWN)

Native `won` still only from the environment.
