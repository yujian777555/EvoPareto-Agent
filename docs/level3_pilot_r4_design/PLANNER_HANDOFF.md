# LEVEL3-PILOT-R4 R2 — Planner Handoff

**From:** Executor  
**To:** Planner (independent review)  
**Round:** `LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX-R2`  
**Git baseline at start:** `d1056059e73b46225dd4218b98a9948af7627b19`  
**New real API requests this round:** **0**

---

## 1. Acceptance report (task-book section 8)

| # | Item | Finding |
|---|---|---|
| 1 | Start/end SHA & sync | start `d105605…`; end see §6; `HEAD == origin/main`; worktree clean after commit |
| 2 | File changes | §2 |
| 3 | D/E implementation status | §3 |
| 4 | Official train SHA / count | `17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465` / **7,473** |
| 5 | Reproducible contamination audit | script + rerun + 6 regression tests |
| 6 | Hash & statistics gate tests | v1 `1771a67c…` reconfirmed; `expected_count` gate added |
| 7 | P vs C budget & power | `RQ3_MULTI_SEED_DESIGN.md` |
| 8 | Test counts (exact JUnit) | targeted **149 passed / 0 failed / 0 skipped**; full **985 passed / 0 failed / 2 skipped**, total 987, RETCODE 0 |
| 9 | R3 results & auth protected | 402 frozen tracked files unchanged; auth `244 / $0.0363972` read-only; R3 `EXPECTED_TASK_HASH` intact |
| 10 | New real API requests | **0** |

---

## 2. Files added / modified

**Modified:** `PREREGISTRATION.md`, `TASKSET_AND_STATISTICS.md`, `BUDGET_AND_EXECUTION_PLAN.md`, `CONFIRMATION_CONTAMINATION_AUDIT.md`, `src/research/r4_paired_stats.py`, `tests/baseline_first/test_r4_design_offline.py`, this file.

**Added:**
* `src/research/r4_workflow_program.py` — Parent adapter / WorkflowProgram
* `tests/baseline_first/test_r4_parent_adapter.py` (14)
* `scripts/level3_pilot_r4/audit_confirmation_contamination.py`
* `tests/baseline_first/test_r4_confirmation_audit.py` (6)
* `docs/level3_pilot_r4_design/RQ3_MULTI_SEED_DESIGN.md`
* `docs/level3_pilot_r4_design/confirmation_contamination_audit_rerun.json`
* `results/level3_pilot_r4_data/gsm8k_train_official.jsonl`
* `results/level3_pilot_r4_data/gsm8k_train_provenance.json`

---

## 3. D/E parent adaptation — answers to the five questions

| Q | Answer |
|---|---|
| 1. AFlow Parent contract | `class Workflow` with `async __call__(problem)` → one `operator.Custom(input=problem, instruction="")`; returns `(response, cost)`; executed by `run_workflow_code_isolated` + Docker IPC + host-side gold |
| 2. WorkflowGenome / AgentGenome | FCEOL node-graph for `offline_evaluator` / categorical agent config. **Neither** can express the R3 Docker-IPC/AFlow contract |
| 3. Real adapter from frozen Parent? | **YES — new, purpose-built:** `src/research/r4_workflow_program.py`. Not a conversion to WorkflowGenome/AgentGenome (that would change semantics) |
| 4. Semantics preserved? | **Unmutated program identity-compiles to frozen `parent_graph.py` (LF).** Parent SHA gates enforced at load (`PARENT_GRAPH_BYTE_SHA256` / `PARENT_GRAPH_LF_SHA256`). Mutations intentionally change semantics and are recorded in `operator_history` |
| 5. Same interface for D and E? | **YES at the program/lineage layer** (`generate_flat_candidates` vs `generate_two_generation_candidates`). Real-model scoring still needs authorized budget |

**D and E implementation status:** `REPRESENTATION_AND_LINEAGE_READY` / `REAL_MODEL_EVAL_BLOCKED_ON_AUTHORIZATION`.  
Not `BLOCKED_IMPLEMENTATION` any more — but **not** claimed as a completed real experiment either.

---

## 4. Contamination audit (reproducible)

* Script: `scripts/level3_pilot_r4/audit_confirmation_contamination.py` (deterministic).
* Rerun: 40/40 `DATA_ONLY`, 0 `SCORED_OR_SELECTED`, independence `CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH`.
* Historical R2 official scored indices: **`[1, 2]`** — not in confirmation set.
* Scan manifest: 1,035 files with SHA-256 recorded in `confirmation_contamination_audit_rerun.json`.
* Regression: known scored question injected under `tmp_path` is flagged `CONTAMINATED_SCORED`.

---

## 5. RQ3 seed design summary

```
TOTAL_REQUESTS(R) = 240 + 240 * R
R=1   480   Plan P  — exploratory SINGLE_SEED_CANDIDATE_COMPARISON_ONLY
R=5   1440  Plan C  — algorithm-level (moderate/large effects)
R=10  2640  Plan C  — wider seed CIs
+10% margin → 528 / 1584 / 2904
```

| Cap | R=1 | R=5 | R=10 |
|---|---|---|---|
| requests ≤ 300 | FAIL | FAIL | FAIL |
| output tokens ≤ 200k | FAIL (high) | FAIL | FAIL |
| cost ≤ $5 | PASS | PASS | FAIL (≈$7.92) |

**Analysis unit for algorithm claims = search seed** (not 40×R tasks).  
Power table and dependence rules in `RQ3_MULTI_SEED_DESIGN.md`.

---

## 6. Execution record

| Field | Value |
|---|---|
| New real API / HTTP model requests | **0** |
| Authorization | read-only; 244 attempts; $0.0363972; not blocked |
| Frozen results | 402 tracked, 0 modified |
| New data file | `gsm8k_train_official.jsonl` only (public download) |
| R3 hash gate | unchanged |
| v0 freeze | unchanged |
| v1 SHA reconfirm | `1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4` |
| Targeted tests | 149 / 0 / 0 |
| Full suite | 985 / 0 / 2 (RETCODE 0) |

---

## 7. Decisions still required from Planner

| ID | Decision | Executor note |
|---|---|---|
| P1 | Accept adapter as D/E representation base | code + 14 tests ready |
| P2 | Accept train data as gen/dev source | verified 7473 / SHA recorded |
| P3 | Choose Plan P vs Plan C (R) | requires new request **and** token authorization |
| P4 | Raise caps (requests, output tokens, maybe cost) | current 300 / 200k / $5 cannot host even Plan P |
| P5 | Accept final preregistration | **not** done in this round |
| P6 | Mark v1 confirmation set accepted | **still PROPOSED** |

---

## 8. Stop statement

`LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX-R2` is complete and **STOPPED**.  
Zero real model requests. No budget change. No final freeze. No preregistration approval.  
Awaiting Planner independent review and explicit user authorization.

