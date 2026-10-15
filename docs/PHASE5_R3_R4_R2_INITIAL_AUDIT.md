# Phase5-R3-R4-R2 — Initial Audit

**Baseline:** `ff75754` · tests green

## P0 confirmations

| id | finding | evidence |
|----|---------|----------|
| P0-1 | `!= "train"` → always OOD | `native_alfworld.py` old line 82 |
| P0-2 | success JSON lacked trajectory | old `horizon_deepseek.json` |
| P0-3 | `.text` discarded usage | `horizon_diagnosis.py` gate.generate(...).text |

## Plan

split_integrity module · full EpisodeRunner traces · structured LLM returns ·
global APICallGate · 402 fail-fast · D2 valid_train H=30 · replay script ·
four-method prereg (no run).
