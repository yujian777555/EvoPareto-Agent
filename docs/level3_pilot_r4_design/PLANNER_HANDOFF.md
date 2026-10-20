# LEVEL3-PILOT-R4 Design Prep — Planner Handoff

**From:** Executor
**To:** Planner (independent review)
**Round:** LEVEL3-PILOT-R4-DESIGN-PREP (zero-cost preparation only)
**Git baseline at start:** `eaca0b87071fa1387d5bd76a045ce247b568ba65` (HEAD == origin/main)
**New real API requests this round:** **0**

---

## 1. Acceptance report (task-book section 10)

| # | Item | Finding |
|---|---|---|
| 1 | Actual baseline and GitHub HEAD | Start and end baseline `eaca0b87071fa1387d5bd76a045ce247b568ba65`; remote `main` unchanged during the round |
| 2 | Modified / added files | See section 2. No tracked results/ file modified |
| 3 | Offline test counts | New file `tests/baseline_first/test_r4_design_offline.py`: **26 passed**. Full suite: **RETCODE 0**, approx. **948 passed, 2 skipped** (Windows symlink), **0 failed** on the final run. One transient failure `test_l3r21_multiprocess.py::test_multiprocess_budget_cap_respected` was observed mid-round (GBK subprocess decode flake on Windows) and passed on isolation re-run and on the final full run |
| 4 | R3 results and historical ledger unchanged | YES. `tests/frozen_guard.snapshot()`: **402** tracked results files, 0 added / 0 removed / 0 modified. `git status results/` empty. Authorization JSON only read |
| 5 | Preregistration parameters still undetermined | U1 `n_conf`, U2 `k`, U3 Group C edit, U4 mutation set, U5 Group E selection, U6 optional Child-replica group, U7 new budget amount, U8 freeze acceptance — listed in `PREREGISTRATION.md` §9 with proposed defaults |
| 6 | Task-set source verification | Official GSM8K **test** VERIFIED (SHA `3730d312...c39d14`, 1319 records). Official **train** **NOT LOCALLY AVAILABLE** → generation/dev freeze BLOCKED. R3 35 items remain SYNTHETIC (0/35 official match) |
| 7 | Budget estimate method and data source | Unit rates from R3 settled ledger (`0.0055302/35`, `0.0154032/105`) and R3 prereg worst-case (`0.525/175`); request counts from group formulas; see `BUDGET_AND_EXECUTION_PLAN.md` |
| 8 | New real API requests | **0** |
| 9 | Git commit / push / workspace | see section 5 after push |
| 10 | Planner decisions needed | **YES** — section 3 |

---

## 2. Deliverables produced

### 2.1 Documents (required)

| File | Purpose |
|---|---|
| `docs/level3_pilot_r4_design/BASELINE_AUDIT.md` | Verifiable baseline: hashes (byte + LF), R3 provenance status, child sampling confound, auth snapshot, test protections, unverifiable items |
| `docs/level3_pilot_r4_design/PREREGISTRATION.md` | RQ1–RQ4, hypotheses + falsifiability, Groups A–E operational definitions, data roles, freeze commitments, stats/stopping rules, U1–U8 |
| `docs/level3_pilot_r4_design/TASKSET_AND_STATISTICS.md` | Source verification, freeze rules, proposed confirmation freeze + SHA, McNemar/Wilson/Holm plan, sample-size ranges |
| `docs/level3_pilot_r4_design/BUDGET_AND_EXECUTION_PLAN.md` | Request/token/cost/latency/success tables, auth gate, **request gap 424**, options O1–O4 |
| `docs/level3_pilot_r4_design/PLANNER_HANDOFF.md` | This file |

### 2.2 Freeze artefact (proposed, not accepted)

| File | Detail |
|---|---|
| `docs/level3_pilot_r4_design/freeze/confirmation_set_proposed.json` | `R4-confirm-v0-proposed`, 40 official GSM8K test tasks, seed 20260601, `task_set_sha256 = 4885c9771a53ad1adc2c0bffaff738e4aed3d0de434f9a39a17cba1fdba6204d` |

Status field: `PROPOSED_PENDING_PLANNER_ACCEPTANCE`. Selection does not use labels. Generation/dev freeze intentionally **not** produced (train missing).

### 2.3 Offline code and tests (justified by Task E)

| File | Why needed |
|---|---|
| `src/research/r4_paired_stats.py` | Task E requires paired stats, McNemar exact, Holm, anomaly detection, task-set hash gate, frozen-unchanged check, budget consistency. No prior shared library covered all of these in one offline module (R3 had inline McNemar in `run_paired_35.py`) |
| `tests/baseline_first/test_r4_design_offline.py` | 26 fixed-sample tests; includes regression values matching R3 `b=2,c=0` one-sided 0.25 / two-sided 0.50; asserts module has no network imports |

No other new code. No Docker, no HTTP, no ledger writes.

---

## 3. Decisions required from Planner (do not auto-resolve)

| ID | Decision | Executor recommendation |
|---|---|---|
| **D1** | Accept or amend `PREREGISTRATION.md` | Accept as v1; any edit before calls is fine, after calls is not |
| **D2** | Accept or regenerate confirmation freeze | Accept `R4-confirm-v0-proposed` (or reseed and issue v1); embed SHA in runner gate |
| **D3** | Unblock official GSM8K **train** acquisition | **Required** before Groups D/E can run; SHA must be verified like test.jsonl |
| **D4** | Or approve labeled policy deviation (use disjoint test slices for selection+confirmation) | Default: **reject**; only if train cannot be obtained |
| **D5** | New request authorization | Full A–E at `n_conf=40` needs **480** calls + margin; remaining **56**. Recommend explicit new cap, not silent downsizing |
| **D6** | Confirm U1–U5 defaults (`n_conf=40`, `k=3`, Group C = +1 verify pass, syntactic mutations, single-generation top-μ) | Accept or replace **before** freeze |
| **D7** | Whether to include optional Child-replica reference arm (U6) | Skip unless a direct R3 replication is wanted |

If D3 is blocked and D4 is rejected, Groups D and E are marked **UNRESOLVED** and RQ3 cannot be answered — they are not deleted.

---

## 4. Scientific guard-rails restated

1. R3 (29/35 vs 31/35, two-sided p=0.50, **synthetic** tasks) is **not** evidence of recursive self-improvement and **not** official GSM8K generalization.
2. The R3 Child is a 3-sample majority-vote workflow. R4 Group B exists specifically to price that confound; Group A vs B is the sampling contrast.
3. Mock / simulated data never enters confirmatory statistics (tests label it `SIMULATED`).
4. Failures stay in the denominator. No task dropping.
5. Estimates are not invoices (`PROVIDER_INVOICE = NOT_VERIFIED`).
6. This work is Level 3 Pilot only — separate from any master's thesis / NSGA-III project.

---

## 5. Execution record (to be finalized at push)

| Field | Value |
|---|---|
| New real API / HTTP model requests | **0** |
| Authorization record | read-only; `physical_attempts=244`, `spent=$0.0363972`, `remaining_requests=56` |
| Frozen results | 402 files, unchanged |
| New tests | 26 offline tests in `test_r4_design_offline.py`, all passing |
| Full suite | RETCODE 0; 2 skipped (Windows symlink) |
| NSGA-III started? | NO |
| R3 taskset/results edited? | NO |
| Commit message prefix | `Research:` (design prep) |

---

## 6. Stop statement

Executor work for LEVEL3-PILOT-R4-DESIGN-PREP is complete and **stopped**. No real experiment was started. No budget was increased. Next step is Planner independent review and explicit user authorization. Executor will not proceed to sampling, candidate generation, or any model call until D1–D5 are resolved in writing.

