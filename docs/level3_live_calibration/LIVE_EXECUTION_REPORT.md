# Live Execution Report

**Run id:** `l3-cal-b1aa792a44`

## Summary

| Metric | Value |
|---|---|
| REAL_MODEL_REQUESTED | deepseek-flash |
| REAL_MODEL_RETURNED | deepseek-flash |
| THINKING_DISABLED_CONFIRMED | True |
| REAL_HTTP_REQUESTS | **2** / 10 |
| LEDGER_REQUESTS | 2 |
| HTTP_LEDGER_MATCH | True |
| REAL_INPUT_TOKENS | 651 / 80000 |
| REAL_OUTPUT_TOKENS | 1000 / 5000 |
| REAL_COST_USD | **0.0005934** / 0.10 |
| STOP_REASON | **DOCKER_CHILD_EXECUTION_FAILED** |

## Stage 1 — real GSM8K math (train)

- status: **OK**
- finish_reason: stop
- non_empty: True · parseable: True
- predicted: `10` (gold `10` for the Weng problem)
- real step-by-step reasoning returned (not a mock)

## Stage 2 — real AFlow-style Optimizer XML

- status: **OK** · finish_reason: stop
- XML complete: **True**
- graph compile: **OK** · has `class Workflow`: True
- prompt compile: **FAIL:invalid syntax**
- CANDIDATE_GRAPH_SHA: `ec852e928b06afdbfcc5af2c7134b720f928bd7eeac0e939f9ae10dc20edd50a`
- modification: Replace single-shot answering with a three-stage graph: plan sub-steps, compute each step with a verification pass, then synthesize the final numeric answer wit

> Finding: the real model produced a **valid compileable Workflow graph**, but the
> `<prompt>` field was not valid Python (`FAIL:invalid syntax`), so the
> module-level `INSTRUCTION` constant expected by the generated graph was not
> injected into the container.

## Stage 3 — Docker + IPC child execution

- docker_ok: **False** · returncode: 1
- ipc_processed: 0 (0 — failed before any model call)
- container task keys: question,task_id (no gold)
- predicted: None · gold (host only): 72 · correct: False
- stderr: `t()
  File "/work/runner.py", line 31, in main
    out = await w(task['question'])
  File "/work/graph.py", line 8, in __call__
    plan = await self.llm(INSTRUCTION + "\nProblem:\n" + problem + "\nList the sub-steps needed to solve this, one per lin`

**Execution failure recorded as EXECUTION_FAILED — no fabricated success.**
No real API quota was spent on the child (failed at import/name resolution).

## Cost reconciliation

{
  "run_id": "l3-cal-b1aa792a44",
  "REAL_HTTP_REQUESTS": 2,
  "LEDGER_REQUESTS": 2,
  "HTTP_LEDGER_MATCH": true,
  "REAL_INPUT_TOKENS": 651,
  "REAL_OUTPUT_TOKENS": 1000,
  "REAL_COST_USD": 0.0005934,
  "MAX_COST_USD": 0.1,
  "MAX_PHYSICAL": 10,
  "under_budget": true
}
