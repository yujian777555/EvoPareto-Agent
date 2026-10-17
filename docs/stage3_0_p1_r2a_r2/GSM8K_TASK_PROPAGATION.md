# GSM8K Task Propagation (Task 4)

**Gate C: PASS**

## Problem

`run_workflow_code_isolated` hard-coded `await w("1+1")` — real questions never
reached the Workflow.

## Fix

`/work/task.json` carries `{task_id, question, gold_answer}`; the runner does
`out = await w(task["question"])`. The question is also embedded in the IPC
prompt so the mock model can return the gold answer, proving the full path.

## Scoring (`src/benchmark/gsm8k_tasks.py`)

```
GSM8K Dataset -> Task ID -> Question -> Isolated Workflow
  -> Budget-Gated LLM -> Output -> Answer Extraction -> Gold Scoring
```

Extractor handles integers, negatives, decimals, thousands separators, `####`
markers, and "no answer". Invalid output scores 0 and **stays in the
denominator** — no silent dropping.

## Split integrity

- search: `gsm8k-train-*` (never the official test set)
- validation: `gsm8k-train-*`
- final test: `gsm8k-test-*` (held out)

`selection_uses_official_test_set = false` is asserted in tests.
