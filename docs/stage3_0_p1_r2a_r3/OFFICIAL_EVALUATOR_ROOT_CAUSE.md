# Official Evaluator Root Cause (Task A)

**EVALUATOR_FAILURE_ROOT_CAUSE** — `adapter_child_ok: [false, false]` had seven
compounding defects, all now fixed:

| # | Defect | Fix |
|---|---|---|
| 1 | adapter did not ship `prompt.py` into the container | `extras_for()` injects `workspace...round_N.prompt` |
| 2 | `tenacity` stub lacked `retry_if_exception_type` | stub completed |
| 3 | `pydantic.BaseModel` stub was `_Any` instance | real `class BaseModel` |
| 4 | official template `Workflow(name, llm_config, dataset)` ctor mismatch | runner tries 5 ctor shapes |
| 5 | `operator.Custom` held the pre-patch LLM | container patches `create_llm_instance` to `ModelIPCClient` |
| 6 | `call_with_format` returned no `response` key | returns `{response, modification, graph, prompt}` |
| 7 | `get_usage_summary()` lacked `total_cost` | added |

## Honest evaluation record (this run)

| round | status | rc | predicted | gold (host) | correct | task_keys |
|---|---|---:|---|---|---|---|
| round_1 | EXECUTION_OK | 0 | 0 | 72 | False | ['question', 'task_id'] |
| round_2 | EXECUTION_OK | 0 | 48 | 72 | False | ['question', 'task_id'] |

**EVALUATED_TASK_COUNT = 2**
**EXECUTION_SUCCESS_COUNT = 2**
**EXECUTION_FAILURE_COUNT = 0**

`DOCKER_CHILD_EXECUTION_OK != TASK_CORRECT`. The mock model answering wrong
(`predicted=48` vs `gold=72`) is a **valid observation**, not a failure —
execution + scoring ran on the real candidate.
