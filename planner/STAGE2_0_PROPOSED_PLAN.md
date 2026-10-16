# Stage 2.0 Proposed Plan (not executed)

**Gate-0 first:** EvalPlus feasibility with new executable genome.

1. Implement 3–5 real genes (planning_depth, verification_policy,
   context_budget, action_selection, cost_gate) behind a feature flag.
2. Phenotype validation: fixed tasks, temperature 0, ≥2 repeats; require
   action/cost distribution differences.
3. **Plan A pilot:** 20 tasks × 20 genomes × 2 seeds = 800 evals, shared
   SQLite budget ledger, caps ≤ 2000 HTTP / ≤ $3.
4. Decision gates (frozen before run):
   - G0a: nonzero pass-rate spread across genomes (not all-0 / all-1).
   - G0b: cost spread ≥ 1.5× between cheap and expensive genomes.
   - G0c: no BillingBlocked / no secret retries.
5. Only if G0a–c pass: upgrade PPEC to **dynamic** preference + run Plan B
   (8 arms, H1 directional).
6. ALFWorld stays in CI as regression, not as paper benchmark.
7. Do not run Stage 2.0 until Planner authorizes the API budget.

Estimate for Stage 2.0 Gate-0: **≤ $3, ≤ 2000 HTTP, ~1 day wall-clock**.
