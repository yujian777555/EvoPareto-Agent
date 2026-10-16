# Real Pilot Protocol (design only — NOT executed)

## Reproduction levels

| Level | Meaning | Status |
|---|---|---|
| 1 Import | deps + official code import | **PASS** |
| 2 Mock pipeline | official algorithm on controlled smoke | **PASS** |
| 3 Native pilot | few real model calls on AFlow benchmark | NOT_EXECUTED |
| 4 Paper-scale | full reproduction | NOT_EXECUTED |

## Level 3 pilot plan (needs Planner)

- **Model:** deepseek-flash (frozen rates) or paper-equivalent.
- **Benchmark:** GSM8K (official AFlow config) + HumanEval as 2nd.
- **Tasks:** 20 GSM8K / 20 HumanEval validation sample.
- **Search:** 5 rounds × sample=2 top-k parents; validation_rounds=1 batch.
- **Capture:** every `experience.json`, `results.json`, `log.json`,
  optimize-LLM prompt/response, per-task scores (fixes Limitation 3).
- **Sandbox:** docker; generated `graph.py` executed only in isolated container
  with network denied, timeout, memory cap.
- **Leakage:** search feedback = validation split only; test split held out.
- **Stop:** budget cap · crash · 3 consecutive format failures.

## Pilot questions

1. Does stock AFlow run end-to-end on fixed model?  
2. Non-zero initial workflow success?  
3. Do children improve over parents?  
4. Enough trace detail to measure duplicate/invalid rates?  
5. Fair-comparison readiness for a future minimal improvement?
