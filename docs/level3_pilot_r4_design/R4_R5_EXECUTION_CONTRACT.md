# R4-R5 Execution Contract

**Zero real API requests.** Evidence layers are never conflated.

## Layer status

| Layer | Evidence | Status |
|---|---|---|
| `SIMULATED_LOCAL` | `execute_program_locally` + HookLLM | **READY** (prior rounds) |
| `SIMULATED_DOCKER_IPC` | `run_workflow_code_isolated` + MockIPC / ModelIPCClient bridge | **READY this round** (6 tests) |
| `REAL_MODEL` | DeepSeek HTTP | **BLOCKED (authorization)** |
| Formal experiment | full A–E / Plan P / Plan C | **NOT APPROVED** |

## Docker/IPC checks (this round)

| Check | Result |
|---|---|
| Docker daemon | 29.3.1 (local Desktop) |
| Frozen Parent identity execution | PASS (`answer_text` contains mock `42`; 1 IPC call) |
| Group C two sequential calls | PASS (2 calls; stage-2 prompt contains stage-1 output) |
| Stage-2 receives stage-1 value | PASS (`draft-stage1-answer` in call[1]) |
| Mutated sampling candidate | PASS (3 calls, majority answer) |
| Invalid graph rejection | PASS (`ok` false; container cleaned) |
| Gold never in prompts | PASS (`SHOULD_NOT_LEAK` absent) |
| Structured answer return | PASS (`answer_text` / `answer_len` / `answer_sha256`) |

## Contract notes

* In-container model object is `ModelIPCClient` (`call_with_format` / async `__call__`), **not** host `_request`.
* AFlow `operator.Custom` stub must use `call_with_format` when present.
* Host-side `llm=IPC()` is the mailbox; it is **not** the in-container LLM object.
* Mock answers are **not** model-capability evidence.

## Open items

* Production AFlow `Custom` operator body is not re-audited line-by-line against the stub (stub is contract-compatible).
* Timeout/cancel paths proven at `SIMULATED_LOCAL`, not under Docker stress.
* `REAL_MODEL` remains authorization-blocked.
