# Real Candidate Deterministic Replay (Task C)

No Optimizer call. No real DeepSeek. Saved Level 3 graph/prompt replayed with
deterministic Mock IPC.

## Execution evidence

| Field | Value |
|---|---|
| DOCKER_EXECUTION_STATUS | **PASS** |
| BUNDLE_LOAD_VALID | True |
| WORKFLOW_EXECUTABLE | True |
| IPC_PROCESSED | **4** |
| IPC_REACHED | True |
| container task keys | ['question', 'task_id'] |
| gold in container | False |
| predicted (mock) | 48 |
| gold (host only) | 72 |
| TASK_CORRECT | False |

The real 3-stage graph (plan → per-step solve → synthesize) ran to completion
and issued **4 model requests** through the mailbox.
Mock math correctness is **not** a DeepSeek capability claim.

## Original graph SHA preserved

`ec852e928b06afdbfcc5af2c7134b720f928bd7eeac0e939f9ae10dc20edd50a` — identical to the live run record.

## Negative / exception cases

{
  "missing_prompt": "REJECTED:PROMPT_FIELD_EMPTY",
  "invalid_python": "REJECTED:GRAPH_SYNTAX_INVALID:invalid syntax",
  "missing_workflow": "REJECTED:GRAPH_MISSING_WORKFLOW_CLASS",
  "wrong_dependency": "PASS_EXEC_FAILED",
  "wrong_dependency_stderr": "ine 10, in <module>\n    import graph as _g\n  File \"/work/graph.py\", line 1, in <module>\n    import module_that_does_not_exist_xyz\nModuleNotFoundError: No module named 'module_that_does_not_exist_xyz'\n"
}
