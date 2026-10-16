# Stage 1.7 Subgoal Planning Design

Module: `src/runtime/subgoal_planner.py`. Runtime: `grounded_planner_v1`.

## Loop

```
Task Goal → GoalSpec → World Facts → Active Subgoal
   → grounded legal candidates → LLM choice → env feedback
   → subgoal verification → continue/revise
```

LLM remains the decision maker. The planner supplies structure; it does not
force expert actions.

## Subgoal states

`PENDING → ACTIVE → SATISFIED / BLOCKED` (+ `UNKNOWN`).

## Generic task relations (no concrete locations)

**look_at_obj_in_light:** EXPLORE → LOCATE_TARGET → ACQUIRE_TARGET → LOCATE_TOOL → USE_TOOL → VERIFY_SUCCESS

**pick_and_place_simple:** EXPLORE → LOCATE_TARGET → ACQUIRE_TARGET → LOCATE_DEST → PLACE_TARGET → VERIFY_SUCCESS

States advance only on environment evidence (`you pick up…`, `you turn on…`,
`you move…`). Pickup failure → BLOCKED then re-PENDING (retry allowed).
Release clears `holding`. `VERIFY_SUCCESS` only SATISFIED on native `won`.

## ExplorationLog

`visited` vs `inspected_no_target` vs `found_target_at` — a single miss does
not permanently ban a location; order is deterministic (admissible order).

## What this is NOT

- Not a rule library of expert routes (Stage 1.5 sequences never imported).
- Not a hidden-state reader.
- Not a new evolutionary Controller.
