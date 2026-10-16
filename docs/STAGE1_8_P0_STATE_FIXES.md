# Stage 1.8 P0 State Fixes

| Issue | Fix | Test |
|---|---|---|
| **A1** wrong-place set `placed=True` | split `object_released` vs `goal_placement_satisfied`; PLACE_TARGET only on object+dest match | `test_wrong_object_correct_destination`, `test_correct_object_wrong_destination`, `test_correct_object_correct_destination`, `test_successful_wrong_place_reopens_acquire` |
| **A2** stale admissible in observe | `observe(..., admissible_after=)`; EpisodeRunner passes post-step set | `test_new_use_action_seen_after_navigation`, `test_stale_use_not_available_after_leave` |
| **A3** SATISFIED never reopened | `_reconcile()` reopens ACQUIRE/PLACE/USE_TOOL on release/wrong-place | `test_acquire_then_release_reopens_acquire`, `test_acquire_then_wrong_place` |

Operator-precedence bug fixed in placement matching (`and`/`or` grouping).
