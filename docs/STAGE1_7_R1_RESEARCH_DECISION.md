# Stage 1.7-R1 Research Decision

## Status

```
READY_FOR_STAGE1_8_REVIEW
```

P0 initialization and state-transition defects are fixed and regression-tested.
Action grounding is target-first and legal. Runtime isolation preserved.
GenericPolicy still 0 wins — attributed to heuristic capability, **not**
planner-state corruption. Per preregistration, GenericPolicy success is not
required to request a tiny real-LLM pilot when mechanisms are correct.

## Twelve questions (summary)

1. **P0 fixed?** Yes — `reset_for_goal`/`ensure_goal`; tests 8/8.  
2. **Why wrong Book/Laptop plans?** empty-goal planner defaulted to place-family; ref-only swap never rebuilt.  
3. **Subgoal lists:** look_at → EXPLORE…USE_TOOL…VERIFY; pick_and_place → …LOCATE_DEST, PLACE…; UNKNOWN → UNSUPPORTED_GOAL.  
4. **Cross-subgoal facts?** `_reconcile()` satisfies LOCATE+ACQUIRE from one pickup.  
5. **Failed place keeps hold?** Yes — `test_unconfirmed_place_keeps_hold`.  
6. **Tool via admissible?** Yes — `use desklamp` visibility.  
7. **Target-first actions?** Yes — `take alarmclock` ranks above `take book`.  
8. **Still revisits inspected places?** Phases tracked; explore completes only on target/full inspect.  
9. **Native offline:** scripted 3/3, neg 3/3, generic 0/3 (+ bowl discovery on gen probe).  
10. **LLM still decides?** Yes — planner only ranks/annotates.  
11. **Genome:** memory/budget real; planner_strategy PROMPT_ONLY.  
12. **Stage 1.8?** Mechanism-correct → **eligible to request** 6-episode real pilot.

## Stage 1.8 design (not executed)

```
3 frozen tasks × 2 runtimes (current | grounded_planner_v1) × 1 G1 × 1 repeat = 6
caps proposal: ≤200 HTTP · ≤$0.04 · same rates · same manifest SHA
PASS: any native won=true in grounded arm OR current still 0 with grounded > 0
```

Requires separate Planner authorization.
