# Phase5-R3-R5 — Four-Method Preregistration

**Status: design frozen for review — Pilot 2 not run.**

## Arms

| Arm | Method |
|-----|--------|
| A | Random Search (`RandomSearchSampler`) |
| B | NSGA-III |
| C | NSGA-III + PEEM |
| D | NSGA-III + PEEM + PPEC |

## Shared conditions

- `deepseek-flash`, ALFWorld TextWorld, **valid_train**
- Horizon **H=30** (fixed for development; reason: proven success floor)
- Genome space unchanged; task manifest hash pinned
- Equal **genome evaluations** and **native episodes**
- Global physical HTTP + $ gate (persistent ledger)
- Same seeds for task sampling and initialization

## Resource ledger (required columns)

genome evals · native episodes · physical HTTP · successful LLM completions ·
tokens in/out · cost · env steps · wall time

Primary comparison: **success rate** and **cost** (Plan B) at equal budget.

## Pilots

0. Offline wiring (done)  
1. Minimal live chain (≤20 HTTP, $0.10) — engineering only  
2. Multi-seed feasibility — **needs Planner budget**

## Sampling

Stratified by task_type from `development_task_pool.json`; no first-N by sort.
Frozen `valid_unseen` unused for tuning; 2 contaminated IDs recorded.
