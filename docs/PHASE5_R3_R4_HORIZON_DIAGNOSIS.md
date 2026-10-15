# Phase5-R3-R4 — Horizon Diagnosis

Split: **valid_train** (development only). FakeLLM + DeepSeek (after 402 recovery).

| Horizon | Episodes | Success | Avg Steps | Budget Exhausted | Progress (state changes / repeats) |
|---------|----------|---------|-----------|------------------|-------------------------------------|
| 10 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| 20 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| 30 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| **10** | 2 | **0** | 10.0 | 0 | **18 / 0 (DeepSeek)** |
| **20** | 2 | **0** | 20.0 | 0 | **38 / 0 (DeepSeek)** |
| **30** | 2 | **1** | 28.5 | 1 | **55 / 0 (DeepSeek)** |

## DeepSeek episode detail (valid_train)

| H | success | steps | termination | goal | progress |
|---|---------|-------|-------------|------|----------|
| 10 | 0 | 10 | max_steps | put a vase in safe | found+open, no pick |
| 10 | 0 | 10 | max_steps | put some vase on safe | found+open |
| 20 | 0 | 20 | max_steps | put a vase in safe | found+pick+open |
| 20 | 0 | 20 | max_steps | put some vase on safe | found+open |
| 30 | 0 | 29 | budget_exhausted | put a vase in safe | found+open |
| **30** | **True** | **28** | **task_success** | put some vase on safe | **found+pick+open** |

## Interpretation

1. **Non-zero native success appears at H=30** (official `won`).
2. Longer horizon → more state changes (18→38→55), **zero** repeated-action loops.
3. H=10/20 fail as `max_steps` after real progress (not budget kill).
4. FakeLLM stalls; DeepSeek makes consistent environment progress.
5. Signal recovery: **success is possible**; 5-step pilots were insufficient.

## Files

`results/native_alfworld/horizon_diagnosis/horizon_{fake,deepseek}.json`
