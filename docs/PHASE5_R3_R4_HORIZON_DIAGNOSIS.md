# Phase5-R3-R4 — Horizon Diagnosis

Split: **valid_train** (development only). FakeLLM + attempted DeepSeek.

| Horizon | Episodes | Success | Avg Steps | Budget Exhausted | Progress (state changes / repeats) |
|---------|----------|---------|-----------|------------------|-------------------------------------|
| 10 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| 20 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| 30 | 2 | 0 | 8.0 | 0 | 2 / 12 (FakeLLM) |
| 10–30 DeepSeek | 6 | 0 | NOT_RUN | NOT_RUN | **API 402 Payment Required** |

## Interpretation

- FakeLLM stalls on first admissible action → `stalled_no_obs_change`; horizon
  increase does not help a non-adaptive policy.
- Repeated actions high (12 per 2 eps).
- DeepSeek horizon ladder **blocked** by billing (402); cannot attribute 0%
  success solely to horizon vs policy vs budget.

## Files

`results/native_alfworld/horizon_diagnosis/horizon_{fake,deepseek}.json`
