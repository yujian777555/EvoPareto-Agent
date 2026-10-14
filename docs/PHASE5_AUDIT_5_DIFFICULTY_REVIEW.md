# Phase5-Audit-5 — Benchmark Difficulty Review

**Priority:** P1 · **Status:** COMPLETE · **Algorithms & task goals:** unchanged
(hardening is environment-scoring only)

## Saturation check (current real-world catalog)

| metric | value |
|--------|-------|
| n tasks | 50 |
| difficulty mean / max | 0.653 / 0.84 |
| ReAct success | **1.0** |
| saturated? | **YES** |

## Hard profile (environment-only)

- difficulty +0.08 (cap 0.98)
- `no_tools` penalized on tool-required tasks
- 3 seeds, μ=10, G=5, tasks=30

| seed | ReAct success | PEEM success | PEEM HV |
|------|---------------|--------------|---------|
| 11 | 1.00 | 0.967 | 0.813 |
| 22 | 1.00 | 0.863 | 0.787 |
| 33 | 1.00 | 0.913 | 0.816 |
| **mean** | **1.00** | **0.914** | 0.805 |

## Finding (honest)

ReAct remains at ceiling (1.0) even under hardening. Population-mean PEEM is
lower because the population contains weak genomes — **not** evidence that PEEM
hurts; but it **does** show mock real-world tasks cannot discriminate methods
for a strong fixed baseline.

## Recommendation (do not inflate PEEM numbers)

1. Paper must state **ceiling effects** on the mock real-world suite.
2. Discriminative evidence comes from **ALFWorld / WebShop / DeepSeek** tables.
3. Future: partial observability, stochastic tool failures, longer horizons —
   as a separate benchmark release, not as post-hoc score chasing.

## Limitations

Hardening used scoring penalties only; no new task *goals* were added (task
catalog frozen for comparability with prior phases).
