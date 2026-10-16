# Stage 1.7-R1 Root Cause Audit

**P0 reproduced and fixed.** Real API: 0.

## P0 initialization defect (confirmed)

Stage 1.7 code:

```python
self._goal_spec = parse_goal("")           # family=UNKNOWN
self._planner = SubgoalPlanner(...)        # _build falls back to pick_and_place_simple
# later on first real goal:
self._planner.goal_spec = self._goal_spec  # ref replace ONLY — subgoals NOT rebuilt
```

Reproduction (pre-fix):

```
empty family UNKNOWN → subgoals [EXPLORE, LOCATE, ACQUIRE, LOCATE_DEST, PLACE, VERIFY]
after look_at goal   → family look_at_obj_in_light but subgoals STILL place-family
```

**Why Book/Laptop could get wrong plans:** `look_at_obj_in_light` episodes
started with empty-goal planner carrying `LOCATE_DEST/PLACE_TARGET` instead of
`LOCATE_TOOL/USE_TOOL`. The agent was steered toward placement semantics.

## Related defects fixed in the same pass

| ID | Defect | Fix |
|---|---|---|
| A2 | UNKNOWN defaulted to pick_and_place | `UNSUPPORTED_GOAL` subgoal list |
| B1 | early facts didn't satisfy later subgoals | `_reconcile()` from world facts |
| B2 | EXPLORE done after 1 visit | only on target evidence / full inspect |
| B3 | failed pickup → held | hold only on `you pick up` feedback |
| B4 | PLACE released before confirmation | release only on confirmed move/put |
| B5 | held vs placed conflicts | conflict → UNKNOWN |
| C2 | unrelated pickup equal to target | target-object +10 ranking |
