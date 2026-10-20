# R4 Execution Pipeline Status (R4-R4)

**Evidence class:** STATUS_INVENTORY (not a real-run result)  
**Real API requests this document round:** **0**

Pipeline stages and their true implementation status.  
READY means offline code + tests exist. NOT RUN means no real-model evidence. BLOCKED means authorization or missing implementation.

| # | Stage | Entry point | Data contract | Error path | Offline tests | Status |
|---|---|---|---|---|---|---|
| 1 | Candidate generation | `generate_flat_candidates` / `generate_two_generation_candidates` + `apply_mutation` | `WorkflowProgram` / `FailedCandidate` | FailedCandidate retained | `test_r4_mutation_seeds.py`, `test_r4_parent_adapter.py` | **READY** |
| 2 | Docker execution | `src/runtime/workflow_ipc.run_workflow_code_isolated` | graph_src + extras + IPC llm | docker_cleanup / CONTAINER_NOT_CREATED | existing R3 tests (not re-proven for R4 programs) | **NOT VERIFIED for R4 programs** |
| 3 | Model call (real) | IPC `_request` → DeepSeek | prompt str → content | ledger RESERVED→SETTLED | — | **BLOCKED (authorization)** |
| 4 | Model call (simulated) | `execute_program_locally` + `_HookLLM` | prompt → str/awaitable | WORKFLOW_* errors | `test_r4_group_c_async.py` | **READY (SIMULATED only)** |
| 5 | Dev-set scoring | `evaluate_workflow_output` (host gold) | predicted vs gold | invalid → incorrect | existing scorer tests | **READY (offline)** |
| 6 | E gen-1 selection | `select_by_dev_accuracy` | program_id → dev score | MISSING_DEV_SCORE raises | adapter tests | **READY** |
| 7 | Gen-2 generation | `mutator(winner, slot)` | same | FailedCandidate | seed audit + tests | **READY** |
| 8 | Final candidate selection | `select_e_final` / D select | 4 candidates + scores | requires exactly 4 | adapter tests | **READY** |
| 9 | Confirmation evaluation | same as 4/5 on freeze v1 | per-task rows | failures stay in denominator | — | **NOT RUN (authorization)** |
| 10 | Budget settlement | `src/runtime/auth_ledger.py` | RESERVED/SETTLED | fail-closed PERSIST_FAULT | budget tests | **READY (code); NOT USED for R4** |
| 11 | Result archive | results/ namespace + frozen_guard | hashed files | immutability check | frozen_guard tests | **READY** |

## Summary layers

| Layer | Status |
|---|---|
| Representation | READY |
| Local mock execution | READY (SIMULATED) |
| Docker execution of R4 programs | NOT VERIFIED |
| Real model | BLOCKED (auth) |
| Formal experiment / final freeze | NOT APPROVED |

**Rule:** mock/simulated outputs must never be filed as real-model results.  
**Rule:** pipeline is **not** claimed READY end-to-end.
