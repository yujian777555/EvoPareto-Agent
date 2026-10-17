# Gold Leakage Elimination (Task A)

**GOLD_LEAKAGE_ELIMINATED = True**

## Problem

The previous mock concatenated `GOLD:{answer}` into the task prompt and wrote
`gold_answer` into `/work/task.json`, so the untrusted Workflow could read the
answer from the prompt, a file, or IPC.

## Fix

| Channel | Before | After |
|---|---|---|
| prompt | `question + "GOLD:"+gold` | `question` only |
| `/work/task.json` | `task_id, question, gold_answer` | **`task_id, question`** |
| IPC request | could carry gold | only `id, prompt` (question) |
| gold location | everywhere | **host trusted scorer only** |

Evidence: `no_gold_leakage_evidence.json` —
`task_json_keys = ["task_id","question"]`, `child_task_keys = ['question', 'task_id']`,
`question_contains_gold_tokens = []`.

The mock model derives answers from numbers **in the question text** (gold-blind).
Correctness is therefore not claimed; the scorer still runs on the host.

## Negative tests

- word-boundary scan: no fixture question contains its gold token as a number
- container `task_keys` observed at runtime: `['question','task_id']`
- Linux Docker symlink/atomic tests: `linux_ipc_security_tests.json`
