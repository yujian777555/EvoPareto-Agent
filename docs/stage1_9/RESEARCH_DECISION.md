# Stage 1.9 Research Decision

## FINAL: `REFINE_METHOD`

Not KEEP (collision + thin novelty). Not STOP (orthogonal channels and strict
budget accounting are salvageable). Not full PIVOT unless Plan A fails.

## Fifteen answers (compressed)

1. **Question worth studying:** refined to *preference-adaptive, budget-aware
   multi-objective agent configuration search* — not generic "PEEM/PPEC improve
   agents".
2. **NSGA-III fit:** not justified at 2 objectives; use NSGA-II headline or
   add a 3rd objective.
3. **PEEM:** operator-utility AOS variant; distinct from archive replay but
   not from classic AOS — `PEEM_INSUFFICIENTLY_NOVEL` standalone.
4. **PPEC:** static reference-direction bias + satisfaction argmax; **not** a
   dynamic controller — `PPEC_INSUFFICIENTLY_NOVEL` standalone.
5. **Joint:** orthogonal (variation vs selection); interaction unproven;
   needs 2×2 factorial.
6. **2024–2026 collisions:** MOAE, Harmony Harness, **RSI-Router (ALFWorld!)**,
   CRAFT, MO-CAPO, RoboPhD — HIGH.
7. **NO-OP genes:** tool_policy; planner_strategy (PROMPT_ONLY); reflection degenerate.
8. **Executable genome:** planning_depth, verification_policy, context_budget,
   action_selection, cost_gate (3–5 real effects).
9. **ALFWorld:** drop as primary; keep as regression/stress only.
10. **Primary benchmark:** EvalPlus HumanEval+/MBPP+.
11. **Cheapest feasibility:** EvalPlus Plan A (~800 evals, $1–2.5).
12. **Attribution:** equal eval budget, ≥5 seeds, bandit-AOS + archive controls,
    anytime HV; no "more calls = better".
13. **Minimal pilot:** 800 evals / $0.8–2.4 / days.
14. **CCF B gaps:** nonzero spread on real benchmark; dynamic PPEC; 8 arms;
    held-out; noise-aware stats.
15. **KEEP / REFINE / PIVOT / STOP:** **REFINE_METHOD** — upgrade PPEC to
    dynamic + prove PEEM beats bandit AOS; else PIVOT to pure
    budget-allocation methodology.

## Next stage (proposed only)

Plan A feasibility on EvalPlus with executable genome; no PEEM/PPEC paper
claims until Gate-0 (performance spread) passes.
