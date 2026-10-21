# MICRO-R3.1 Integration Report

**Real API:** **0** · Cost **$0** · Baseline `78444c1…`

## Production execution chain

Unified entry: `src/research/r3_docker_executor.execute_candidate_docker` →
`src/runtime/workflow_ipc.run_workflow_code_isolated` (Docker + IPC mailbox).

| Requirement | Status |
|---|---|
| P/R/F/E2 same contract | YES |
| Executes `graph_source` (not instruction-only) | YES |
| Records program_id / parent / generation / graph SHA | YES |
| Parent unmutated graph = frozen SHA | YES (`a92febff…`) |
| Child graph SHA = child candidate | YES (`graph_sha256_match`) |
| `executed_graph_source` evidence-based | YES (`evidence_executed_graph`) |
| Compile/container/IPC/timeout failures not success | YES |

## Offline E2E (SIMULATED_DOCKER_IPC)

`scripts/level3_pilot_r4/r31_e2e_validation.py` →
`results/level3_pilot_r4_micro_r31_offline/r31_e2e_validation.json`

* Parent dev failures → coarse `ANSWER_MISMATCH` feedback  
* F operator from policy; E2 from gen-1 winner (generation=2)  
* Splits 10/5/8 disjoint; 21 prior indices excluded  
* Reproducible mutations under fixed seed  
* Confirm paired interface (no reverse selection)

Mock outputs are **fixture-driven** (`SIMULATED`), not gold-generated answers.

## Budget (corrected)

| Block | Requests |
|---|---:|
| Parent dev (feedback source) | 5 |
| R + F dev | 10 |
| E2 dev | 5 |
| Confirm P + winner + E2 (8×3) | 24 |
| S probe (3×2) | 6 |
| **Baseline total** | **50** |
| **+10% margin (suggested cap)** | **55** |

Cost estimate worst-case ≈ $0.036–$0.045; suggest **$0.05** cap.

`NO_QUALIFIED_ERROR_ARCHIVE` unchanged — real F feedback comes only from
**authorized Parent dev runs**, not history.

## Status

`Docker/IPC executor READY (offline)` · `R/F/E2 lineage READY` ·  
`Real model run NOT authorized` · `RSI/NSGA-III NOT claimed`


## R3.2 fixes

- Mock mailbox: task-level fixtures; unconfigured raises; no silent default.
- E2 feedback now from **gen-1 winner** FailureRecords (not Parent summary).
- Real entry scripts/level3_pilot_r4/run_micro_r3.py (Docker/IPC + independent ledger + pre-send reserve).
- Mock rehearsal: 0 real requests, . Budget plan: **50 baseline / 55 cap / .05**.
