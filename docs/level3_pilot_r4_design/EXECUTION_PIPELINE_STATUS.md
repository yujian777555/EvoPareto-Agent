# R4 Execution Pipeline Status (R7)

**Evidence class:** STATUS_INVENTORY — not a real-run result.  
**Real API requests this document round:** **0**

## Evidence layers (do not conflate)

| # | Layer | Meaning | Status |
|---|---|---|---|
| 1 | `SIMULATED_LOCAL` | in-process HookLLM | READY |
| 2 | `SIMULATED_DOCKER_IPC` | Docker + stub Custom / mock mailbox | READY |
| 3 | `PRODUCTION_ADAPTER` | real AFlow `Custom`/`call_with_format` + **mock model** | READY (Parent identity only) |
| 4 | R4 full candidate gen → evolve select → dev score → confirm score | complete A–E / Plan P pipeline | **NOT READY / NOT RUN** |
| 5 | R4 real authorization ledger integration | `AUTH_PATH` controlled grant + `auth_ledger` settle | **NOT WIRED for R4 real runs** (gate exists; no approved grant) |
| 6 | `REAL_MODEL` | DeepSeek HTTP | **BLOCKED** |

**Parent PRODUCTION_ADAPTER success does NOT make layers 4–6 READY.**

## Host-side HTTP gate (R7)

`src/runtime/r4_http_gate.py` is invoked at the start of `src/backend/http_client.post_json` **before any socket**.  
`verify_execution_allowed` re-validates full config + policy + seeds + AUTHORIZED grant bound to `config_sha256`.  
PROPOSED / unknown config status, missing/corrupt grant, or budget over remaining → `R4HttpBlocked`.  
Container-generated code cannot install this gate.

## Per-stage table (unchanged honesty)

| Stage | Status |
|---|---|
| Candidate generation / lineage | READY (offline) |
| Docker R4 programs | SIMULATED / PRODUCTION_ADAPTER only |
| Real model call | BLOCKED |
| Dev-set scoring | READY offline |
| Confirmation evaluation | NOT RUN |
| Budget settlement (R4) | code READY; no R4 grants issued |
| Formal experiment / freeze / prereg | **NOT APPROVED** |
