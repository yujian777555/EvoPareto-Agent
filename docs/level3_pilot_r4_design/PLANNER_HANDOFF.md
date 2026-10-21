# LEVEL3-PILOT-R4 R7 — Planner Handoff

**Baseline:** `0ce4e0305a3bb928a3b81c91139c3dd072b038bf`  
**Real API:** **0** · Auth read-only · R3 / v1 confirm / PHASE2 bytes unchanged

---

## P0 — execution gate bypass closed (Task A)

| Fix | Detail |
|---|---|
| Contradiction removed | freeze config **cannot** carry `execution_authorized` (`EXEC_AUTH_FIELD_FORBIDDEN_IN_CONFIG`) |
| Separate grant | `AuthorizationRecord` bound to `config_sha256` + `version` + quotas; source `controlled_file` on real path |
| Strict allow-list | config status must be `APPROVED_FOR_EXECUTION` / `FROZEN_ACCEPTED`; PROPOSED/DRAFT/unknown **fail closed** |
| Entry re-validates | `verify_execution_allowed` always runs full structure + `R4-BUDGET-POLICY-v1` + seeds |
| No loose snapshot on real path | `allow_test_injection=False` rejects `source=TEST` |
| Host HTTP gate | `r4_http_gate` at start of `post_json` **before socket**; `R4HttpBlocked` |
| Attack tests | 19 auth + 4 HTTP = all reject with **socket count 0** |

## Task B — audit exclusions

* **No substring excludes.** Exact POSIX paths + `REVIEWED_NON_TEXT_EXCLUSIONS` only.
* Every skip logged with path/SHA/size/reason/`rule_id`.
* Unknown same-name copies (official jsonl, audit-like names, freeze copies) are **scanned**.
* `PHASE2_EVOLUTION_MEMORY.md` unchanged; independence stays **`CONFIRMATION_INDEPENDENCE_BLOCKED`**.

## Task C/D — IUT + seeds

* F2 = **IUT** {E−D, E−C} decided; F2-a/b/c language removed/superseded.
* E−D and E−C **co-primary**; joint claim needs both.
* `BASE_SEED=20260601` fixed in code; config cannot redefine; R values must be true ints.

## Task E — evidence layers

`SIMULATED_LOCAL` / `SIMULATED_DOCKER_IPC` / `PRODUCTION_ADAPTER` / **R4 full pipeline NOT READY** / **auth ledger not wired for R4** / `REAL_MODEL BLOCKED`.

## Tests (JUnit this round)

| Suite | passed / failed / skipped |
|---|---|
| Budget P0 | 18 / 0 / 0 |
| Auth bypass | 19 / 0 / 0 |
| HTTP gate | 4 / 0 / 0 |
| Audit | 27 / 0 / 0 |
| Stats | 14 / 0 / 0 |
| IPC/Freeze | 24 / 0 / 0 |
| Historical | 76 / 0 / 0 |
| **Full** | **1123 / 0 / 2** (1125) RETCODE 0 |

## Integrity

R3 0 modified · R3 gate unchanged · v1 `1771a67c…` · PHASE2 `abab3a36…` · auth 244 / $0.0363972.

## STOP

No execution freeze approval, no preregistration approval, no real model experiment. Awaiting Planner review.
