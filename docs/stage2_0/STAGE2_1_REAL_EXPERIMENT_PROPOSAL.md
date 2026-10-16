# Stage 2.1 Real Experiment Proposal (NOT executed)

**Prerequisite:** Planner approval + budget. Real LLM calls in Stage 2.0 = 0.

## Task family

Code generation with verify/diagnose/repair loop (EvalPlus HumanEval+/MBPP+
subset). Real agent workflow: GENERATE → VERIFY (run tests) → DIAGNOSE →
REPAIR → SUBMIT. Structure genes map to real code paths (add test step,
add retry loop, change routing, change context).

## Arms (equal budget)

1. Random Evolution  
2. Fitness-only Evolution  
3. Global AOS  
4. LLM Diagnosis + Repair (single-shot)  
5. Failure-guided Heuristic Evolution (fixed map)  
6. **FCEOL**

Same: seed genomes, mutation set, task split, model, eval count, budget ledger.

## Scale estimate (needs approval)

- Pilot: 20 tasks × 30 interventions × 6 arms ≈ 3,600 evals ≈ **$5–15**.
- Report: held-out pass rate, Δ distribution, negative transfer, budget caps.

## Frozen success criteria (proposed)

- FCEOL held-out Δ > Global AOS (paired, ≥3 seeds, bootstrap CI).
- Shuffled-label control strictly worse.
- No secret retries; all calls in one SQLite ledger.
