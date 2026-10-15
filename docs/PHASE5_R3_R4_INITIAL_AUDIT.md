# Phase5-R3-R4 — Initial Audit

**HEAD:** `7c000f5` · tests green · Docker alfworld ready

## Findings

| id | issue | status this phase |
|----|-------|-------------------|
| B1 | post-hoc assert budget in micro pilot | **FIXED** `APICallGate` pre-reserve |
| B2 | `len//4` tokens treated as real | **FIXED** ledger separates estimated vs actual |
| B3 | only 2 games / 5-step horizon | **FIXED** pools + H1/H2/H3 diagnosis |
| B4 | efficiency rewards quick-fail | **CONFIRMED** by counterexample (see objective validity) |
| B5 | robustness ≡ f(perf) | **CONFIRMED** redundant at perf=0 |
| B6 | autonomy = config proxy | candidate behavior metric documented |
| B7 | valid_unseen contamination | 2 games recorded in frozen manifest |
| B8 | four-method native fairness | wiring audited; no equal-budget multi-seed yet |
| B9 | DeepSeek | **HTTP 402 Payment Required** during diagnosis |

## API budget evidence

`src/runtime/api_budget.py` — reserve → attempt → settle; retries consume
budget; failed sends count as spent.
