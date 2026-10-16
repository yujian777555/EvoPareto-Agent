# Stage 1.7 Action Semantics

Module: `src/runtime/action_semantics.py` (deterministic parser).

## ActionSpec

```
ActionSpec(action_type, object, source, target, raw_command, parse_ok)
```

| Type | Example command | Fields |
|---|---|---|
| NAVIGATE | `go to shelf 3` | target |
| INSPECT | `examine book 2` | object |
| OPEN / CLOSE | `open drawer 1` | target |
| PICKUP | `take book 2 from sidetable 1` | object, source |
| PLACE | `move alarmclock 1 to dresser 1` / `put X in/on Y` | object, target |
| USE_TOOL | `use desklamp 1` | object, target |
| LOOK | `look` | — |
| UNKNOWN | `fly to moon` | parse_ok=False |

## Hard rules

1. Input is always the **live** `admissible_commands` list.
2. Parser never constructs commands; `relevant_candidates` returns only inputs.
3. Instance numbers come from the environment (e.g. `shelf 3` seen in admissible).
4. Object names are not navigable locations (`go to desklamp` is not generated).
5. Unparseable → `UNKNOWN`, no guessing.
6. Execution effects require environment feedback (see shared_repair evidence rules).

`relevant_candidates(admissible, goal_spec, subgoal)` ranks legal commands by
the active subgoal kind, with NAVIGATE fallback for discovery — no per-task
location priority lists.
