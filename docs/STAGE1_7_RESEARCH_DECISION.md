# Stage 1.7 Research Decision

## Status

```
PLANNING_MECHANISM_INCOMPLETE
```

Offline semantics and subgoal machinery **work** (Gates A–D PASS), but the
**generic observation-driven policy still fails** to complete tasks on native
ALFWorld (0/3). Scripted sequences only prove wiring.

## Q&A (12)

1. **A1–A4 fixed?** Yes — `results/stage1_7/semantic_tests.json`.
2. **GoalSpec from public text?** Yes — `goal_grounding.parse_goal` + tests.
3. **ActionSpec mapping?** Yes — 9 types, UNKNOWN fallback, admissible-only.
4. **Active Subgoal maintained?** Yes — evidence transitions in `subgoal_planner`.
5. **Still loops?** Generic policy reduced examine-loops but still no win in 20 steps.
6. **Discovery/hold/release/won from env?** Yes — feedback regexes + native `won` only.
7. **Oracle leakage?** No — modules scanned; expert sequences only in offline control scripts.
8. **grounded_planner_v1 changes decisions?** Prompt + candidates change; LLM still chooses; scripted path executes subgoal-relevant actions.
9. **Native offline?** Scripted 3/3 PASS (control); generic 0/3 FAIL/INCONCLUSIVE; negative 3/3 PASS.
10. **planner_strategy phenotype?** PROMPT_ONLY / tree_search UNIMPLEMENTED; memory/budget real.
11. **Stage 1.8 justified?** **Not yet** — generic policy must show non-zero completion first.
12. **What PEEM/PPEC could optimize?** Only if genomes yield different grounded-action distributions; currently at risk of degeneracy.

## Scientific collision risk (Task G)

| Question | Assessment |
|---|---|
| Shared planner = benchmark fix or new method? | **Engineering baseline** — generic subgoal scaffolding; not a paper novelty by itself |
| Does it erase Genome differences? | Risk: if planner candidates dominate, LLM/Genome effect shrinks — monitor paired trajectories |
| Hard-coded answers? | None in `src/runtime/*`; expert sequences isolated in offline tests |
| PEEM/PPEC still meaningful? | Only with real Performance/Cost variation across genomes after planning works |
| Distinct from existing agent planning? | Subgoal/grounding is standard practice — must not be sold as the paper's core innovation (that remains NSGA-III+PEEM+PPEC) |

## Next (needs Planner)

Improve **generic** multi-step execution (e.g. subgoal-aware action ranking +
goal-relevant inspect) until ≥1 native win **without** scripted answers, then
request tiny Stage 1.8 pilot (3 tasks × 2 runtimes × 1 repeat = 6 real episodes).

**No real API this round.**
