# Stage 1.7-R1 Planner Fixes

Files: `src/runtime/subgoal_planner.py`, `src/runtime/action_semantics.py`,
`src/runtime/interactive_agent.py` (ensure_goal).

## A1 reset / ensure

```python
planner.reset_for_goal(goal_spec)   # full rebuild (new episode / task switch)
planner.ensure_goal(goal_spec)      # rebuild only if fingerprint changed
```

Fingerprint = `family|object|receptacle|relation`. Same goal keeps episode
progress; different goal clears `held`, `world_facts`, `exploration`.

## A2 UNKNOWN

`task_family not in {look_at_obj_in_light, pick_and_place_simple}` →
single `UNSUPPORTED_GOAL` subgoal (BLOCKED). Prompt states
`UNSUPPORTED_GOAL: cannot build a grounded plan`.

## B1–B5 state machine

`_reconcile()` re-evaluates all non-SATISFIED subgoals from confirmed facts
after every feedback update. Pickup/place/tool facts come from environment
phrases (`you pick up…`, `you move…`, `you turn on…`), never from command names
alone.

## C2 relevance

`relevant_candidates(..., held_objects=)` ranks by goal-object match first;
unrelated PICKUP scores below navigation. Output always ⊆ admissible.

## C3 truncation

Planner block lists top 12 candidates (target-first); full admissible list
still in prompt (up to 40) and parser accepts any legal command.
