# Output Protocol Fix (Task B)

## Problem

`build_runner_script` printed `repr(out)[:500]` as the scoring payload. Long
responses were truncated before scoring; a parent `(response, cost)` tuple had
its cost embedded in the same string.

## Fix

The container now emits a **structured, fully-serialised** JSON record:

```json
{{"ok": true, "task_id": "...", "answer_text": "<full text>",
  "answer_len": N, "cost_meta": "<cost repr or null>",
  "out_kind": "tuple|plain", "question_len": N, "task_keys": [...]}}
```

- `answer_text` is never truncated — logs may truncate, scoring data may not.
- Parent tuple is split: `answer_text` = response, `cost_meta` = cost.
- Regression tests assert a 600+ char response survives to the scoring layer.

## Tracking fields for future ledger rows

task_id · candidate SHA · request phase · prompt SHA · physical request id ·
full response SHA · token usage · finish_reason.

## Regression tests (5)

1. long response not truncated before scoring
2. parent tuple separates text from cost
3. intermediate numbers / cost not mistaken for the answer (`\boxed{6}` wins)
4. existing ledger rows carry the required tracking fields
5. rescore statistics are internally consistent
