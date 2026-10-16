# Stage 1.6 Research Decision

## Situation

Both `current` and `shared_repaired` failed all 6 episodes (12/12 total `won=false`).
Offline gates all passed; the environment is solvable (Stage 1.5 / Gate C);
the shared repair **changed prompts but not outcomes**.

## Decision

```
SHARED_REPAIR_INSUFFICIENT
```

Do **not** expand to G2/G3. Do **not** start evolutionary arms. The problem is
not (only) missing memory/stagnation state — it is **task planning and
ALFWorld action semantics**.

## What the evidence says

| Observation | Implication |
|---|---|
| Loop occurrences unchanged (18.3 both arms) | progress block alone does not break examine/go-to loops |
| Object discovery still rare | agent does not search shelves/dressers for hidden targets |
| Gate C: 4-step scripted plans win | relation steps exist and are short |
| Stage 1.5 positive controls win in 7–18 steps | budget is enough; planning is not |

## Minimal next diagnosis (needs Planner, not executed)

1. **Action-semantics grounding**: ALFWorld verbs (`use desklamp`, `move X to Y`)
   and where objects live (shelf 3, sidetable 2) — often mis-targeted.
2. **Subgoal decomposition for multi-hop goals**: find → take → navigate →
   toggle/place; the agent currently collapses into local examine loops.
3. Optional: **one** targeted mechanism test (e.g. explicit subgoal checklist
   in prompt) as a *shared* baseline change, not an evolutionary variable.

Avoid stacking more runtime machinery before the agent can chain 3–4
goal-relevant actions.

## Gate summary

```
GATE1: FAIL (repaired 0/6)
GATE2: REPAIR_NOT_SUPPORTED (0 vs 0)
GATE3: PASS (cost ratio 1.22)
GATE4: no loop reduction
```

## Bottom line

Memory/stagnation/goal-state block is correctly wired and safe, but **not
sufficient**. Next step is a small shared planning/semantics study — not a
larger evolutionary search.
