# Phase5-R3-R4 — Final Report

## 1. Git

| item | value |
|------|-------|
| Commit | this SHA |
| origin/main | pushed |
| working tree | clean |

## 2. Environment

ALFWorld 0.4.2 / TextWorld 1.7.0 · multiple task types in pools ·
**50 dev + 30 frozen test** manifests · 2 contaminated IDs recorded.

## 3. Horizon Sensitivity

| Horizon | Episodes | Success | Avg Steps | Budget Exhausted | Progress |
|---------|----------|---------|-----------|------------------|----------|
| 10 | 2 | 0 | 8.0 (Fake) | 0 | state_chg 2, repeats 12 |
| 20 | 2 | 0 | 8.0 (Fake) | 0 | same pattern |
| 30 | 2 | 0 | 8.0 (Fake) | 0 | same pattern |
| DS 10/20/30 | NOT_RUN | — | — | — | **402 Payment Required** |

## 4. Objective Audit

See table in `PHASE5_R3_R4_OBJECTIVE_VALIDITY.md` —
**efficiency / robustness / autonomy invalid for main tables**.

## 5. API

| item | value |
|------|-------|
| status | **HTTP 402 Payment Required** |
| successful calls this phase | 0 |
| failed | ≥1 (402) |
| budget gate | pre-reserve implemented & tested |
| tokens | estimated vs actual separated in ledger |

## 6. Algorithm Integrity

RS independent · NSGA-III/PEEM/PPEC wiring intact · equal-budget multi-seed
native comparison **not run** (API).

## 7. Evidence

| question | answer |
|----------|--------|
| non-zero success? | **NO** |
| trustworthy intermediate progress? | FakeLLM: stall only; DeepSeek: unknown |
| failure cause | policy stall + budget exhaust + **billing block** |
| worth scaling? | **NOT YET** |

## 8. Paper Decision

- Keep **performance** (env won) and **cost** (API) as primary.
- **Do not** put efficiency/robustness/autonomy in main tables until Plan A
  protocol is approved.
- PEEM/PPEC superiority hypothesis remains **untested** on native success signal.

## 9. Final Status

**`BLOCKED_API`**

(DeepSeek billing 402 prevents required diagnosis; offline audit complete.)
