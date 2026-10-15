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
| status | **RECOVERED** (was 402; retest OK) |
| horizon diagnosis calls | 118 (DeepSeek `deepseek-flash`) |
| tokens | in ~23k class / out recorded in horizon JSON |
| budget gate | pre-reserve implemented & used |

## 6. Algorithm Integrity

RS independent · NSGA-III/PEEM/PPEC wiring intact · equal-budget multi-seed
native comparison still pending (now unblocked).

## 7. Evidence

| question | answer |
|----------|--------|
| non-zero success? | **YES — 1/2 at H=30 (valid_train)** |
| trustworthy intermediate progress? | **YES** (found/pick/open + state_changes 18→55) |
| failure cause | short horizon `max_steps` (not budget-only) |
| worth scaling? | **YES** — propose pilot at H=20–30 on dev pool |

## 8. Paper Decision

- **performance (env won) is measurable** with adequate horizon.
- efficiency/robustness/autonomy still need Plan A protocol.
- Next: equal-budget 4-method pilot on **valid_train** only.

## 9. Final Status

**`ACCEPTED_SIGNAL_READY`**

(Native success signal recovered after horizon fix + API recovery.)
