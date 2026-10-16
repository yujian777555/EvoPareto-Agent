# Stage 1.8 Research Decision

## Status

```
GROUNDED_SOLVABILITY_NOT_ESTABLISHED
```

Both runtimes 0/3 on the three debug tasks. Grounded planner increased cost
and loops without improving discovery. The multi-step planning structure is
correct offline but **not sufficient** for real DeepSeek to complete tasks.

## Twelve questions

1. **A1–A3 fixes?** Yes — placement split, admissible_after, reopen tests.  
2. **Wrong place ≠ success?** `goal_placement_satisfied` only on object+dest match.  
3. **admissible_after before planner update?** Yes — `EpisodeRunner` passes post-step set.  
4. **Satisfied → reopen?** Yes on release/wrong-place (`test_acquire_then_release_reopens_acquire`).  
5. **Current unchanged?** Yes (Gate C).  
6. **Grounded sends subgoals/candidates?** Yes (prompt block in `grounded_planner_v1`).  
7. **6/6 executed?** Yes, no skips/dups.  
8. **Successes:** current 0, grounded 0.  
9. **Discovery:** current 2/3 discovered target; grounded **0/3** — worse.  
10. **Ledger:** 180 HTTP, $0.02478, 360 settled, 0 retries.  
11. **Initial solvability?** **Not observed** with real LLM on these tasks.  
12. **Genome validation next?** **No** — first fix why LLM+grounding fails to act on goal objects.

## Honest interpretation

Offline mechanism correctness ≠ real task competence. The agent still loops;
grounded candidates may over-emphasize navigation. Continuing to stack
planner modules is unlikely to help.

## Recommended next (needs Planner)

Stop adding planning layers. Re-examine **base agent ↔ benchmark fit**:
(1) inspect/act granularity of DeepSeek on ALFWorld verbs; (2) shorter
horizon with forced goal-directed inspect; or (3) accept that these
multi-hop tasks need a different action interface. Do **not** run PEEM/PPEC
trials until ≥1 unscripted native win exists.
