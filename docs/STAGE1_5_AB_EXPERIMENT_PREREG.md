# Stage 1.5 A/B Experiment Preregistration

**Design only — not executed. Requires Planner budget approval.**

---

## Question

Does the **shared repaired runtime** (recorder + stagnation + goal-state in the
prompt/memory path) improve native `won` vs the **current runtime**, holding
genome and tasks fixed?

## Matrix

```
3 frozen tasks (0, 10, 20)
  × 1 genome (G1: cot/short_term/self_critique/balanced/64)
  × 2 runtimes (current | shared_repaired)
  × 2 seeds (11, 23)
= 24 episodes
```

Optional extension (if budget allows): +G2 block (12 more episodes).

## Frozen protocol

| Item | Value |
|---|---|
| model | `deepseek-flash` |
| rate_version | `deepseek-flash-2026-10-peak-conservative-v1` |
| split | `valid_train` |
| horizon | 30 |
| objective | `candidate_2obj` (native won, cost) |
| tasks | manifest indices 0,10,20 (SHA `27b54ac0…`) |
| shared ledger | one SQLite for the batch |
| caps (request) | 24 episodes · 800 HTTP · $0.10 estimated |

## Critical: Stage 1 is NOT the control arm

Stage 1 results are **historical diagnostics**. Model conditions, order, and
logging may differ. The `current_runtime` arm must be **re-collected in the
same batch** for a fair paired comparison.

## Preregistered pass / fail (frozen)

| Gate | PASS | FAIL / inconclusive |
|---|---|---|
| A/B solvability | ≥1 `won=true` in repaired arm | 0 in both → shared repair insufficient |
| A/B improvement | repaired arm wins on ≥2 matched (task, seed) blocks vs current | tie/negative → repair not supported |
| Cost safety | repaired arm cost ≤ 1.5× current median | cost explosion → redesign |

Statistical limits: n=2 seeds are **not** independent controlled replicates
(`SEED_NOT_EFFECTIVE_FOR_LIVE_POLICY`). Report per-episode outcomes; do not
claim significance on n=2.

## Budget estimate (`ab_budget_estimate.json`)

| | HTTP | Cost |
|---|---:|---:|
| Median (30 HTTP, $0.0027/ep) | 720 | $0.065 |
| Recommended cap | 800 | $0.10 |

## Prohibitions

- No automatic execution.
- No task/genome changes after results.
- No progress-proxy as formal performance.
- No PEEM/PPEC comparison until solvability gate passes.
