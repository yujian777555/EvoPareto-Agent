# Stage 1.7 Runtime Implementation

## Variants

| Variant | Status | Behavior |
|---|---|---|
| `current` | unchanged | Stage 1 prompt only |
| `shared_repaired` | unchanged | + progress/stagnation block |
| **`grounded_planner_v1`** | **new, default off** | + GoalSpec + Active Subgoal + grounded candidates |

`grounded_planner_v1` activates only when explicitly passed to
`EpisodeRunner(..., runtime_variant="grounded_planner_v1")` /
`InteractiveAgent(...)`.

## Prompt addition (planner variant)

```
Active Subgoal:
- kind=ACQUIRE_TARGET target=alarmclock status=ACTIVE
Current World Facts:
- holding: ...
- visited_locations=[...]; found_target_at=...
Legal Action Candidates related to subgoal:
- go to shelf 3  [NAVIGATE]
- take alarmclock 1 from shelf 3  [PICKUP]
```

Candidates are **only** commands from the live admissible set.

## Isolation

- No edits to PEEM/PPEC/NSGA-III/ObjectiveSpec/billing gate.
- Historical results untouched.
- `current` / `shared_repaired` prompts unchanged (Gate C tests).

Files: `src/runtime/{goal_grounding,action_semantics,subgoal_planner}.py`,
updates in `interactive_agent.py` (variant switch + observe).
