# LEVEL3-PILOT-R4 R3 — Planner Handoff

**From:** Executor  
**To:** Planner (independent review)  
**Round:** `LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX-R3`  
**Git baseline at start:** `08af0e6cab458febb94a44d0ca87f5343af4bb78`  
**New real API requests this round:** **0**

---

## 1. Acceptance report (task-book section 6)

| # | Item | Finding |
|---|---|---|
| 1 | Start/end SHA & sync | start `08af0e6…`; end see §7; `HEAD == origin/main` |
| 2 | File changes | §2 |
| 3 | D/E execution pipeline | §3 |
| 4 | Group C status | §4 |
| 5 | Contamination audit per-task + gates | §5 |
| 6 | RQ3 pairing / power / task dependence | §6 |
| 7 | Budget & token caps | §6.2 |
| 8 | Exact test counts | targeted **173 / 0 / 0**; full **1009 / 0 / 2**, RETCODE 0 |
| 9 | R3 frozen + auth integrity | 404 tracked results (incl. prior train data), 0 modified; auth `244 / $0.0363972` read-only; R3 gate unchanged |
| 10 | New real API requests | **0** |

---

## 2. Files added / modified

**Modified:** `src/research/r4_workflow_program.py`, `tests/baseline_first/test_r4_parent_adapter.py`, `scripts/level3_pilot_r4/audit_confirmation_contamination.py`, `tests/baseline_first/test_r4_confirmation_audit.py`, `docs/level3_pilot_r4_design/{PREREGISTRATION,TASKSET_AND_STATISTICS,BUDGET_AND_EXECUTION_PLAN,RQ3_MULTI_SEED_DESIGN,CONFIRMATION_CONTAMINATION_AUDIT,PLANNER_HANDOFF}.md`, `confirmation_contamination_audit_rerun.json`.

**Added:** `scripts/level3_pilot_r4/rq3_power_tables.py`, `docs/level3_pilot_r4_design/RQ3_POWER_TABLES.txt`, `tests/baseline_first/test_rq3_power_tables.py`.

---

## 3. D/E actual execution pipeline status

| Layer | Status | Evidence |
|---|---|---|
| Representation | **READY** | `WorkflowProgram`, SHA gates, `MutationPlan` (fixed ops/probs/pool/LCG seed), lineage |
| D generation | **READY** | `generate_flat_candidates` — 4 slots all from Parent; failures kept as `FailedCandidate` (dev=0) |
| E generation | **READY** | `generate_two_generation_candidates` — gen1 from Parent; winner by `select_by_dev_accuracy` (creation-order ties); gen2 from winner; `select_e_final` over all 4 |
| No-op / failure policy | **READY** | `NOOP_MUTATION` rejected; failed slots retained, never dropped |
| Vote ties | **READY** | first-occurrence majority (`next(v for v in votes…)`), not `set` order |
| Local mock execution | **READY** | `execute_program_locally` (SIMULATED hook, ctor probes, answer extraction, error paths) |
| Docker + real model | **NOT RUN** | authorization-gated |
| Formal experiment | **NOT APPROVED** | — |

---

## 4. Group C status

**IMPLEMENTED** as `build_group_c_fixed_verify`:

* Parent single call + **one** fixed verification (`GROUP_C_CHECK_INSTRUCTION`).
* Calls = 2; `fixed_verify=True`; not a sampling mutation.
* Distinct from `mutate_add_check_stage` (sampling-path only).
* Offline tests cover definition, rejection on sampling parents, and two-call mock execution.

---

## 5. Contamination audit

* Verdict classes: `NO_HIT`, `ALLOWED_SOURCE_ONLY`, `PROTOCOL_DECLARED_HIT`, `HISTORICAL_SCORED_HIT`, `INCONCLUSIVE_SCAN`.
* No-hit is **not** auto-`DATA_ONLY`.
* Official SHA + count and freeze `verify_task_set(..., expected_count=40)` are **gates**: failure → `CONFIRMATION_INDEPENDENCE_BLOCKED`.
* Rerun this round: official gates OK; freeze gate OK (`1771a67c…`, n=40); **40/40 `NO_HIT`**; R2 prior-scored indices `[1,2]` recorded; independence **VERIFIED_BY_ARTIFACT_SEARCH**.
* Tests (10): hash tamper blocks, missing official blocks, known scored question flagged, verdict matrix, determinism.

---

## 6. RQ3 multi-seed design (fixed)

### 6.1 Pairing & tests

* Seeds: `plan_seed[r] = BASE_SEED + 1009*r`, recorded in freeze.
* **Paired block:** D and E share `MutationPlan` seed in block `r`; slots 0–1 same draws from Parent; E slots 2–3 from winner.
* **Exact two-sided Wilcoxon at R=5 has p_min = 0.0625 → cannot reject α=0.05.** Need **R≥6** (prefer 10).
* If pairing is not implemented → Mann–Whitney (independent), not fake pairing.
* Plan P (R=1) = `SINGLE_SEED_CANDIDATE_COMPARISON_ONLY` (no σ_d claim).
* Task dependence: seed-difference claims are **conditional on the frozen 40 tasks**; distributional claims need pre-specified crossed (task×seed) analysis.
* Failed seeds: primary = accuracy 0 retained; sensitivity = complete-case.

### 6.2 Budget (unified, margins included)

```
TOTAL_REQUESTS(R) = 240 + 240 * R
WITH_MARGIN(R)    = ceil(1.1 * TOTAL)
```

| R | TOTAL | +10% | vs 300-cap | worst USD | out high (800/req) |
|---:|---:|---:|---:|---:|---:|
| 1 | 480 | 528 | FAIL | $1.58 | 422k FAIL >200k |
| 5 | 1440 | 1584 | FAIL | $4.75 | 1.27M FAIL |
| 6 | 1680 | 1848 | FAIL | $5.54 cost FAIL | 1.48M FAIL |
| 10 | 2640 | 2904 | FAIL | $8.71 FAIL | 2.32M FAIL |

Authorization unchanged. Real experiments remain **authorization-gated**. v0 hash preserved; v1 `1771a67c…` unchanged.

---

## 7. Execution record

| Field | Value |
|---|---|
| New real API / HTTP model requests | **0** |
| Authorization | read-only; 244 / $0.0363972 / not blocked |
| Frozen results | 404 tracked, 0 modified this round |
| R3 `EXPECTED_TASK_HASH` | intact |
| v0 / v1 freeze | v0 unchanged; v1 reconfirmed `1771a67c…` |
| Targeted tests | 173 passed / 0 failed / 0 skipped |
| Full suite | 1009 passed / 0 failed / 2 skipped (RETCODE 0) |

---

## 8. Stop statement

`LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX-R3` is complete and **STOPPED**.  
Zero real model requests. No budget change. No final freeze. No preregistration approval.  
Awaiting Planner independent review and explicit user authorization.
