# Confirmation-Set Historical Contamination Audit (R4-RF)

**Evidence class:** REPRODUCIBLE_OFFLINE_AUDIT  
**Baseline commit:** `766a610d43712332ad9187ac926c03376ce509b6`  
**Audit target:** proposed 40-task confirmation set (v0 and v1, same membership)  
**Official source baseline:** `results/level3_pilot_r31/gsm8k_test_official.jsonl`  
- SHA-256 **recomputed this round**: `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`  
- Record count **recomputed this round**: **1319**  
- Matches previously published digest: **YES**

**New real API requests this round:** **0**  
**Original R3 results / ledgers / old task lists:** **not modified**

---

## 1. Question

Were any of the 40 proposed confirmation tasks (or their official indices) previously used for model debugging, candidate selection, or scoring? If so, they are contaminated and must be excluded under a pre-declared rule.

---

## 2. Method (not filename-based)

For each of the 40 tasks:

1. Take the **full normalized question text** (whitespace-collapsed) and 70–140 character fragments.
2. Search every `.json/.jsonl/.md/.py/.txt/.csv/.yml` under `results/`, `docs/`, `scripts/`, `tests/`, `src/` (excluding `external/`, `.git`, `__pycache__`), plus structured `index` fields and `gsm8k-official-test-NNNN` IDs.
3. Classify every hit as:
   - **DATA_ONLY**: appears only in the official source file and/or the freeze draft
   - **SCORED_OR_SELECTED**: appears in an experiment result, ledger, rescore, replay, or selection log
   - **DECLARED_ONLY**: index reserved in protocol/manifest but question never executed
4. Do **not** infer non-use from file names alone.

Raw machine output (first pass): `confirmation_contamination_audit_raw.json`.

**Reproducible audit program (R4-R2):** `scripts/level3_pilot_r4/audit_confirmation_contamination.py`  
Rerun output: `confirmation_contamination_audit_rerun.json` (deterministic, `sort_keys=True`).  
It records the scan roots/suffixes/exclusions, SHA-256 of every scanned file, per-hit classification, and R2 prior-scored official indices `[1, 2]`.  
Regression tests: `tests/baseline_first/test_r4_confirmation_audit.py` (6 tests, including a SIMULATED injection that flags a historically scored official question as `CONTAMINATED_SCORED`).

Rerun summary: `n_data_only=40`, `n_scored_or_selected=0`, `n_declared_only=0`, `independence=CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH`, `scan_file_count=1035`.

---

## 3. Findings

### 3.1 Question-text hits for the 40 tasks

| Location | Hits (of 40) | Classification |
|---|---:|---|
| `results/level3_pilot_r31/gsm8k_test_official.jsonl` | 40 | **DATA_ONLY** (official source) |
| `docs/level3_pilot_r4_design/freeze/confirmation_set_proposed.json` | 40 | **DATA_ONLY** (this design draft) |
| Any `results/` scoring/ledger/replay file | **0** | — |
| Any `scripts/` / `tests/` / `src/` code | **0** | — |
| Offline fixture `src/benchmark/gsm8k_tasks.py` | **0** | — |

### 3.2 Historical official-GSM8K model use (different tasks)

| Artefact | Official test indices actually matched by question text | Used for model scoring? | Overlap with our 40? |
|---|---|---|---|
| `results/level3_pilot_r2/paired_confirmation_set.json` (12 tasks) | **1, 2** | **YES** (Parent 0/12, Child 11/12, parent reverify, rescore_from_ledger) | **NONE** |
| `results/level3_pilot_r3/paired_confirmation_set_35.json` (35 tasks) | **none (0/35 official match)** | YES (but on **synthetic** questions) | **NONE** (content) |
| Mock E2E (`run_full_aflow_mock.py`, `run_official_evaluator_e2e.py`) | offline fixture only | mock provider only | **NONE** |

### 3.3 Index-number collisions (not content contamination)

| Collision | Detail | Judgment |
|---|---|---|
| R3 `gsm8k-test-0013/0027/0036` `index` field = 13/27/36 | R3 questions are **different text** from official index 13/27/36 (verified exact-match = False) | **NOT contaminated** — ID/index reuse of a **synthetic** bank |
| `results/stage3_0_p1_r2a/gsm8k_split_manifest.json` IDs `gsm8k-test-0000..0049` | Claims "official test set indices" in `source` string, but content is the synthetic bank (see R3.1 provenance audit: 0/35 official match) | **NOT content contamination**; source string is historically overstated |

### 3.4 Protocol reservation note

`src/benchmark/gsm8k_protocol.py` declares `FINAL_TEST_INDICES = list(range(0, 20))` as "official test tasks, held out".

| Proposed index | In 0–19 reservation? | Ever scored with a model? |
|---|---|---|
| **13** | YES | **NO** (question text absent from all scoring artefacts) |
| 27, 36, 92, … 1300 (39 others) | NO | NO |

**Judgment:** index 13 is **RESERVED_NOT_SCORED**. Confirmation is the final-evaluation role, so retaining 13 is policy-aligned. It is **not** scored contamination. If Planner wants to leave the entire historical reservation untouched, exclusion of 13 is available as an optional pre-declared rule — it was **not** applied in v1.

---

## 4. Per-task conclusion (all 40)

| Field | Value |
|---|---|
| Tasks with prior model scoring / selection / debug use | **0 / 40** |
| Tasks present only in official source + freeze draft | **40 / 40** |
| Tasks with index-only numeric collision (different text) | 3 (13, 27, 36) — declared `NOT_CONTAMINATED` |
| Tasks in protocol FINAL_TEST reservation | 1 (index 13) — `RESERVED_NOT_SCORED` |

---

## 5. Exclusion rule (pre-declared) and result

Rule (fixed before any re-draw, no performance information used):

1. Exclude any official index whose **question text** appears in any prior model scoring / selection / debug artefact.
2. Exclude empty / duplicate IDs at freeze time.
3. Do **not** select or exclude by expected model performance.
4. Optional (not applied): exclude indices in historical `FINAL_TEST_INDICES` 0–19 reservation.

Applied result: **zero exclusions**. Membership of v1 equals v0.

---

## 6. Independence verdict

**`CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH`**

Not `CONFIRMATION_INDEPENDENCE_UNVERIFIED`: question-level and artifact-level search found no prior model use of these 40 items. Residual risk (cannot prove a negative about processes that used official `test.jsonl` by index without persisting question text) is low in this repo because every real task set has persisted questions (`paired_confirmation_set*.json`).

Known prior model use of **other** official test items (indices 1, 2 in R2) is recorded and stays out of R4 confirmation.

---

## 7. Hash versions after this audit

| Version | File | `task_set_sha256` | Membership |
|---|---|---|---|
| v0 | `freeze/confirmation_set_proposed.json` | `4885c9771a53ad1adc2c0bffaff738e4aed3d0de434f9a39a17cba1fdba6204d` (legacy separators) | 40 tasks |
| v1 | `freeze/confirmation_set_v1_proposed.json` | `1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4` (canonical, see `TASKSET_AND_STATISTICS.md`) | **same 40 tasks** |

v0 is preserved unchanged. Hash change is **serialization only**, not a re-draw.

---

## 8. What was not done

* No R3 result / ledger / authorization mutation.
* No claim that the confirmation set is "frozen and accepted" — still **PROPOSED**, Planner must accept.
* No performance-based redraw.
* No real model requests.

