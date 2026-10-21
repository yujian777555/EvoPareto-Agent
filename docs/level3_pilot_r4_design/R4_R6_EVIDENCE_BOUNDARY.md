# R4-R6 Docker/IPC Evidence Boundary

| Layer | Meaning | Status |
|---|---|---|
| `SIMULATED_LOCAL` | in-process HookLLM | READY |
| `SIMULATED_DOCKER_IPC` | Docker + **stub** Custom | READY |
| `PRODUCTION_ADAPTER` | Docker + **real** AFlow `workspace/GSM8K/.../operator.py` + `scripts/operators.py` `_fill_node`/`call_with_format`, mock model | **READY (this round)** |
| `REAL_MODEL` | DeepSeek HTTP | **NOT RUN / BLOCKED** |

## Production contract (verified against source)

* `Custom.__call__`: `prompt = instruction + input` (concatenation).
* `_fill_node` → `await llm.call_with_format(prompt, formatter)` (GenerateOp `single_fill`) or `await llm(prompt)`.
* Return dict includes `response`.

Test `test_parent_with_production_aflow_adapter` runs frozen Parent through the **real** operator sources in Docker with `MockIPC` mailbox. Result: `ok=True`, `answer_text="Answer: 42"`, one IPC round-trip.

## Not claimed

Mock answers are not model-capability evidence. `REAL_MODEL` remains unverified until an authorized live call.
