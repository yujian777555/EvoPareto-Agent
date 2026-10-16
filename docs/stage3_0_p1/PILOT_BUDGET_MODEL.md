# Pilot Budget Model

Accounting units: `workflow_generation_calls` (optimize LLM) ·
`candidate_evaluation_calls` (exec LLM × tasks × internal calls) ·
`logical_model_calls` · `physical_http_requests` · tokens in/out ·
`estimated_cost` (deepseek-flash peak conservative) · `observed_cost`.

Per round ≈ 1 optimize call + validation_rounds×tasks exec calls; each task
episode ≈ 1–4 LLM calls depending on generated workflow.

| Plan | Bench | Candidates | Tasks/eval | Rounds | Logical calls | HTTP | Est. cost |
|---|---|---:|---:|---:|---:|---:|---|
| Minimum | GSM8K | 5 | 20 | 5 | ~205 | ≤300 | **$0.6–1.5** |
| Normal | GSM8K+HumanEval | 10 | 50 | 10 | ~1010 | ≤1500 | **$5–12** |
| Worst | both | 10 | 50 | 10 | ~1010+retries | ≤3000 | **≤$25** |

**Proposed hard cap: $30** · fail-closed SQLite ledger (reuse PhysicalBudgetGate),
no reset, stop on cap. Uncertainty: workflow length varies tokens; cache/retry
billing unknown; prices may change.

`BUDGET_ESTABLISHED_PROVISIONAL` — **not authorized** until Planner approves
Level 3.
