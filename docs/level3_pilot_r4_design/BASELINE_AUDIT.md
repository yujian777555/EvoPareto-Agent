# LEVEL3-PILOT-R4 Design — Baseline Audit

**Evidence class:** OFFLINE_REPRODUCIBLE_AUDIT (no new model calls)
**Git baseline:** `eaca0b87071fa1387d5bd76a045ce247b568ba65`
**Audit time:** 2026-06 (R4 design prep)
**Scope:** EvoPareto-Agent Level 3 Pilot only. Independent of any master's thesis / NSGA-III work.

---

## 1. Git and workspace baseline

| Check | Result |
|---|---|
| Remote `origin/main` HEAD | `eaca0b87071fa1387d5bd76a045ce247b568ba65` |
| Local `HEAD` | `eaca0b87071fa1387d5bd76a045ce247b568ba65` |
| `HEAD == origin/main` | **YES** |
| Working tree | clean (no staged/unstaged tracked changes) |
| Recent commit chain | `eaca0b8` CI → `bd09419` Audit → `e111625` tests → `a794318` gate → `ea83f95` fix → `aa3f836` audit → `c7b2329` R3 experiment |
| Prior stage acceptance | R3.1-R1 **CONDITIONAL_ACCEPTANCE**; CI path-filter gap closed in `eaca0b8` |

No remote divergence detected. Safe to write R4 design artefacts.

---

## 2. Frozen parent and child candidates

Source directory: `results/level3_pilot_r2/frozen_candidates/`

### 2.1 Hash inventory (byte-level and LF-normalized)

Windows `write_text()` emits CRLF; `read_text()` normalizes to LF. Both digests are recorded because graph SHA checks historically failed when only one form was compared.

| File | Bytes | SHA-256 (byte) | SHA-256 (LF-normalized) |
|---|---:|---|---|
| `parent_graph.py` | 815 | `ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e` | `a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe` |
| `parent_prompt.py` | 48 | `34b149ab37e571def0875faeac171867c3a2bb9fff03db4bc0ccca034e48e979` | `89758a63470c31c0...` |
| `child_graph.py` | 713 | `9aeb265c7c512883...` | `a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b` |
| `child_prompt_raw.txt` | 80 | `97822ed47362e8b331ace3d9e8b8d51309f879a9040cb3c710eda8e7a5fa5be5` | same |
| `child_prompt.py` | 98 | `3aead4c3eb219173...` | `6b773b969598060e32c18f409d2277f4707f9e67152b25357aa111e855f41579` |
| `freeze_manifest.json` | 1082 | `10d8dd2f02003342...` | `35efd137fc4c4ba9...` |

**Canonical digests used by the project** (from `freeze_manifest.json` and R3 results):

| Artefact | Canonical SHA-256 | Form |
|---|---|---|
| Parent graph | `ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e` | byte |
| Parent graph (R3 per-task field) | `a92febff3c94d065812af510f97b06a070dd2603e4daa9b27fdc11f24ab9e4fe` | LF-normalized |
| Child graph | `a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b` | LF-normalized |
| Child bundle | `035b51cb257718d8d300ce4793984f8c115ca9efb443f433d01195c94cace173` | bundle |
| Model | `deepseek-flash` (shared by parent and child) | — |

### 2.2 What the two candidates actually do (operational reading of source)

This is the single most important baseline fact for R4. The two graphs are **not** comparable at equal inference budget.

**Parent (`parent_graph.py`)** — one `Custom` call with empty instruction; returns `(response, cost)`.

```python
solution = await self.custom(input=problem, instruction="")
return solution['response'], self.llm.get_usage_summary()["total_cost"]
```

**Child (`child_graph.py`)** — three parallel draft solves, majority vote over `Answer:` tails, and a fourth "check" call only when the vote is not already a strict majority:

```python
drafts = await gather(*[self.llm(f"{self.solve}\n{problem}") for _ in range(3)])
votes = [d.strip().split("Answer:")[-1].strip() for d in drafts]
best = max(set(votes), key=votes.count)
if votes.count(best) >= 2:
    return best
final = await self.llm(f"{self.check}\nProblem: {problem}\nCandidate: {drafts[0]}")
```

**Implication for R4:** the R3 Parent-vs-Child contrast confounds at least three factors:

1. workflow structure change (single-shot → multi-stage),
2. extra inference sampling (3–4 calls vs 1 call per task),
3. any effect of the Optimizer-produced instruction text.

R3 cannot attribute the observed net +2 to "evolutionary self-improvement". R4 must isolate these factors (see `PREREGISTRATION.md`).

### 2.3 Prompt contract

Child prompt is serialized as `INSTRUCTION = repr(text)` in `child_prompt.py`; graph source is never rewritten. Loader binds `INSTRUCTION` from the prompt module. `freeze_manifest.json` records `prompt_contract: SERIALISED_INSTRUCTION_REPR` and `SHA_VERIFIED: true`.

---

## 3. Task-set provenance

### 3.1 R3 task set (used for the 29/35 vs 31/35 result)

| Item | Value | Verified? |
|---|---|---|
| File | `results/level3_pilot_r3/paired_confirmation_set_35.json` | present |
| `n_tasks` | 35 | yes |
| `task_set_sha256` | `ddf055537d4618c86d736d4f0ed98fd4b23efec21f9e0ffe65a2c8ee022a6219` | yes (full 64-hex gate in `run_paired_35.verify_taskset`) |
| Seed | 20261019 | recorded |
| Declared `source` field | "GSM8K official test split" | **FALSE** |
| Official match count | **0 / 35** | provenance audit `dataset_provenance_audit.json` |
| Classification | 35/35 `SYNTHETIC_OR_UNMATCHED` | yes |
| Exclusion rule | 12 previously used ids excluded, frozen before sampling, no performance-based selection | recorded |

**Provenance audit facts** (`results/level3_pilot_r31/dataset_provenance_audit.json`):

- Official source: `https://github.com/openai/grade-school-math/blob/master/grade_school_math/data/test.jsonl`
- Official file SHA-256: `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`
- Official record count: 1319
- Local verified copy: `results/level3_pilot_r31/gsm8k_test_official.jsonl` (byte-SHA matches official, 1319 lines)
- Match rule: whitespace-run collapse then exact text match; gold = text after last `####`
- Result: 0 question matches, 0 gold mismatches (because 0 matched)

**Conclusion:** the R3 35 questions are synthetic GSM8K-style tasks. Task IDs of the form `gsm8k-test-NNNN` **do not** correspond to official test indices. R3 results are an *exploratory workflow comparison on synthetic tasks*, **not** official GSM8K generalization. This classification must not be reversed.

### 3.2 Official GSM8K availability for R4

| Item | Status |
|---|---|
| Official test.jsonl present locally | YES (`results/level3_pilot_r31/gsm8k_test_official.jsonl`) |
| Byte SHA matches published official digest | YES (`3730d312...c39d14`) |
| Record count | 1319 |
| Format | `{"question": ..., "answer": "...\\n#### <gold>"}` |
| Can R4 freeze a verifiable official task set? | **YES, in principle** — subject to Planner-approved selection rules (see `TASKSET_AND_STATISTICS.md`) |
| Already frozen for R4? | **NO** — freeze is a design deliverable of this round; final acceptance is Planner's decision |

### 3.3 Project-internal task infrastructure

| Module | Role | Notes |
|---|---|---|
| `src/benchmark/gsm8k_protocol.py` | split policy | Explicit rule: train = search/validation only; **test = held-out evaluation only**. Evolution must never select on test. |
| `src/benchmark/gsm8k_tasks.py` | offline fixture + scoring | Contains fixed offline fixture tasks (REAL GSM8K-style with known gold) for mock E2E; distinct from R3 synthetic bank |
| `src/benchmark/gsm8k_split.py` / `split_integrity.py` | split integrity | present |
| `scripts/level3_pilot_r31/audit_gsm8k_provenance.py` | provenance audit | deterministic, side-effect free |

**Policy constraint already encoded:** evolutionary selection must use train-split tasks only; official test is evaluation-only. R4 design must keep this separation.

---

## 4. Historical Parent/Child paired results (R3)

Source: `results/level3_pilot_r3/paired_experiment_results.json`, `final_gate_decisions.json`, and `results/level3_pilot_r31/statistical_correction.json`.

| Quantity | Parent | Child |
|---|---:|---:|
| Correct | 29 | 31 |
| Total | 35 | 35 |
| Accuracy | 82.86% | 88.57% |
| HTTP requests | 35 | 105 |
| Usage cost estimate (USD) | 0.0055302 | 0.0154032 |
| Mean calls per task | 1.0 | 3.0 |

**Paired structure (from raw per-task records, recomputed offline):**

| Cell | Count |
|---|---:|
| Child correct, Parent wrong (improved) | 2 |
| Child wrong, Parent correct (regressed) | 0 |
| Both correct | 29 |
| Both wrong | 4 |
| Net gain | +2 |
| Discordant pairs | 2 |

**Inferential status:**

| Test | Value | Significant at α=0.05? |
|---|---:|---|
| McNemar exact, one-sided | p = 0.25 | NO |
| McNemar exact, two-sided | p = 0.50 | NO |

The R3 report used one-sided p=0.25. The formal claim must quote two-sided p=0.50 unless a one-sided test was preregistered with direction. **Neither is significant at n=35.** `RECURSIVE_SELF_IMPROVEMENT_PROVEN = false`, `NSGA3_EVIDENCE_SUFFICIENT = false`.

### 4.1 Per-task metadata availability

Each of the 70 per-task records (35 parent + 35 child) contains: `task_id`, `role`, `gold_answer`, `graph_sha256`, `latency_s`, `docker_ok`, `docker_cleanup` (container_id, cleaned, error, container_created), `ipc_processed`, `predicted`, `correct`, `raw_output_full`, `answer_sha256`.

| Field class | Available? | Notes |
|---|---|---|
| Correctness / gold | YES | host-side gold, never in container/prompt/IPC |
| Latency (s) | YES | per task per role |
| Docker lifecycle | YES | created/cleaned/error recorded |
| Per-task request count | PARTIAL | parent=1, child=3 (from `ipc_processed` and totals); individual HTTP attempt logs live in ledger DBs |
| Per-task token in/out | PARTIAL | settled totals in auth record; per-call token breakdown in `paired_budget_*.sqlite` ledgers |
| Per-task USD | PARTIAL | `cost_usd_estimate` aggregates exist; per-call settled costs in ledger |
| Provider invoice | **NOT_VERIFIED** | estimate ≠ vendor bill |

---

## 5. Authorization and budget state (READ-ONLY snapshot)

Source: `~/.evopareto/state/level3_pilot_authorization.json` (not modified this round).

| Field | Value |
|---|---|
| `auth_id` | `level3-pilot-authorization-v1` |
| Cap: max physical requests | 300 |
| Cap: max cost USD | 5.00 |
| Cap: max tokens in / out | 2,000,000 / 200,000 |
| Consumed: physical_attempts | **244** |
| Consumed: spent_cost_usd | **0.0363972** |
| Consumed: actual tokens in / out | 10,622 / 27,605 |
| Reserved outstanding | 0 cost, 0 tokens |
| Unknown usage count | 0 |
| `blocked` | false |
| Remaining physical requests | **56** (300 − 244) |
| Remaining cost USD | **≈ 4.9636** |
| Provider invoice | NOT_VERIFIED |
| State files | `level3_pilot_authorization.json`, `.lock`, `.migration.json` |

**Hard constraints carried forward:**

- Do not restore quota by changing Run ID, deleting the DB, changing DB path, or resetting the authorization record.
- Usage estimates are **not** provider invoices.
- New real API requests this round: **0**.

---

## 6. Protective test inventory (offline)

Tracked frozen results files: **402** (`git ls-files results/`). Guard: `tests/frozen_guard.py` (SHA snapshot + diff + `assert_frozen_unchanged`).

| Protection | Primary tests | What it guards |
|---|---|---|
| Task-set hash gate | `tests/baseline_first/test_r31r1_hash_gate.py` (14 tests) | full 64-hex `EXPECTED_TASK_HASH`, field completeness, ID uniqueness, ordering, recomputed==declared==expected, runs before HTTP/credential/budget |
| Budget persistence / auth ledger | `test_l3r2_budget_persistence.py`, `test_r21_atomic_settle.py`, `test_r22_cross_process_persist.py`, `test_hard_budget.py`, `test_r3_provider_budget.py` | create-only authorization record, OS file lock, RESERVED→SETTLED state machine, fail-closed `PERSIST_FAULT`, no quota restore via reset |
| Scoring integrity | `test_r231_rescore_failclosed.py`, `test_r236_cleanup_scoring.py`, `test_r22_output_protocol.py`, `test_r23_output_complete.py` | host-side gold only; `CONTAINER_NOT_CREATED` cannot score; no silent truncation (`repr(out)[:500]` class of bugs) |
| Docker / IPC isolation | `test_r235_popen_cleanup.py`, `test_r231_bounded_output.py`, `test_l3r21_production_e2e.py` | `--network none`, `--cidfile`, explicit `docker rm -f`, bounded 4MB capture, `cleanup_fn` always called |
| Frozen results immutability | `tests/frozen_guard.py` + conftest hooks | any test write to tracked `results/` is detected |
| Candidate hash verification | `test_l3r2_bundle_reliability.py`, freeze manifest | graph/bundle SHA match before admission |

Typical full-suite status at last stage close: **919 passed, 2 skipped (Windows symlink), 0 failed**.

---

## 7. Information that could NOT be verified in this audit

1. **Provider invoice / vendor bill.** Only internal usage estimates and ledger settlement exist. Status stays `NOT_VERIFIED`.
2. **Temporal ordering of R3 preregistration vs first API call.** `paired_confirmation_set_35.json` and `paired_experiment_results.json` land in the same commit `c7b2329`. Git cannot prove within-commit ordering. `PREREGISTRATION_TIMING.independently_verified = false`.
3. **Whether R3 child "check" path ever fired.** Totals show exactly 105 child requests for 35 tasks (=3.0/task), consistent with unanimous majority vote every time, or with check calls accounted elsewhere. Per-call ledger inspection would be needed; not done this round.
4. **Token-level split for every historical call.** Aggregate in/out tokens are in the auth record; full per-call token attribution for older stages was not re-audited.
5. **Any claim that R3 shows recursive self-improvement.** Not supported by the evidence class above. Do not upgrade.

---

## 8. Baseline conclusions for R4 design

1. The frozen Parent and Child candidates are intact and hash-verified; keep them as **Group A** reference and as one point in the design space.
2. The R3 result (net +2, two-sided p=0.50, synthetic tasks) is **not** evidence that evolution works. It is evidence that a multi-sample workflow can edge out a single-shot workflow on 35 synthetic items.
3. The child's 3× sampling budget is the dominant confound. **R4's Group B (Sampling Control) exists specifically to price that confound.**
4. A verifiable official GSM8K test file is available and hash-verified. R4 should freeze from it under a published selection rule — not reuse the synthetic 35.
5. Remaining request quota is only **56 of 300**. A full A–E confirmation study cannot fit in the remaining quota. Budget gap must be reported, not silently truncated (see `BUDGET_AND_EXECUTION_PLAN.md`).

**Stop condition for this audit:** baseline is recorded; no model calls; no budget mutation; no R3 artefact modified.

