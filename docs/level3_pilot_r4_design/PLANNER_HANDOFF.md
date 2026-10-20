# LEVEL3-PILOT-R4 Design Prep / RF — Planner Handoff

**From:** Executor  
**To:** Planner (independent review)  
**Rounds:**  
1. `LEVEL3-PILOT-R4-DESIGN-PREP` (commit `766a610`)  
2. `LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX` (this round)

**Git baseline at RF start:** `766a610d43712332ad9187ac926c03376ce509b6` (HEAD == origin/main)  
**New real API requests across both rounds:** **0**

---

## 1. RF acceptance report

| # | Item | Finding |
|---|---|---|
| 1 | Actual HEAD / origin/main | see section 5 after push |
| 2 | Modified files | `PREREGISTRATION.md`, `BUDGET_AND_EXECUTION_PLAN.md`, `TASKSET_AND_STATISTICS.md`, `src/research/r4_paired_stats.py`, `tests/baseline_first/test_r4_design_offline.py`, this file |
| 3 | Test counts (exact, JUnit) | **Targeted** (R4 offline + R3 hash gate + GSM8K + budget + scoring): **126 passed, 0 failed, 0 skipped, RETCODE 0**. **Full suite: 962 passed, 0 failed, 2 skipped (Windows symlink), total 964, RETCODE 0** |
| 4 | R3 results / ledger / auth unchanged | YES. `git diff 766a610 -- results/` empty; frozen_guard **402** files; auth `physical_attempts=244`, `spent=0.0363972` (read-only); R3 `EXPECTED_TASK_HASH` runner + `test_r31r1_hash_gate.py` **byte-identical** to baseline |
| 5 | Undetermined prereg parameters | U1–U8 still open (Planner must freeze before any call); U5 redesigned (see below) |
| 6 | Task-set source | Official test SHA **recomputed**: `3730d312…c39d14`, 1319 records. Official **train** still **BLOCKED** |
| 7 | Budget estimate method | unchanged unit rates from R3 settled ledger / worst-case precheck; D/E request formula rewritten |
| 8 | New real API requests | **0** |
| 9 | Commit / push | section 5 |
| 10 | Planner decisions needed | **YES** — section 3 |

---

## 2. What RF changed (by task)

### Task A — Group D/E identifiability

| Group | Old (R4 design prep) | **New (R4-RF)** |
|---|---|---|
| **D** | "Random Mutation + Fixed Selection", m=4 from Parent | **Random Search**: exactly 4 mutants, **all from frozen Parent**, each scored on shared dev set, pick max dev accuracy, tie → frozen order `cand_d1..d4` |
| **E** | "(1+λ) single generation, top-μ" | **Two-Generation Evolution**: 2 mutants from Parent → pick gen-1 winner on dev → 2 mutants **from winner** → score **all 4** on same dev set → pick best; tie → `e1a<e1b<e2a<e2b` |
| Match | unequal / underspecified | **m=4, s=20, n_conf=40, equal HTTP 120 vs 120, same confirmation set, same operator distribution** |
| Claim | "evolutionary selection" loosely | E−D isolates **lineage only**; **not** recursive self-improvement |

**Implementation feasibility (honest):** clone-and-mutate operators exist (`fceol/mutation_operators.py` `g.clone()`, `evolution/operators.py` `genome.replace`). Generational protocol is expressible. **Adapter from frozen AFlow `parent_graph.py` to those genome types is NOT implemented.** Until that adapter is hashed into the freeze file, Group E is `SPECIFIED_NOT_IMPLEMENTED` / would be `BLOCKED_IMPLEMENTATION` at run time. It must **not** be silently replaced by random search.

### Task B — Confirmation contamination

Full report: `CONFIRMATION_CONTAMINATION_AUDIT.md` (+ raw JSON).

| Check | Result |
|---|---|
| Official test SHA / 1319 records reverified | YES |
| 40/40 questions in prior model scoring/selection/debug | **0** |
| 40/40 only in official source + freeze draft | YES |
| R2 real official use | indices **1, 2** — **not** in our 40 |
| R3 | synthetic; index-number collisions 13/27/36 are **different questions** |
| Index 13 vs `FINAL_TEST_INDICES` 0–19 | `RESERVED_NOT_SCORED` (declaration only) |
| Verdict | `CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH` |
| Exclusions applied | **0** (rule frozen: exclude prior-scored official indices; 1,2 already absent) |

### Task C — Canonical hash

| Rule | Value |
|---|---|
| Sort | by `task_id` ascending |
| Payload | JSON array of `[task_id, question, gold_answer]` |
| `json.dumps` | `ensure_ascii=False, separators=(",", ":"), sort_keys=False` |
| Encoding / digest | UTF-8 / SHA-256 hex |
| Ref | `src/research/r4_paired_stats.canonical_task_set_sha256` |

| Version | SHA | File |
|---|---|---|
| v0 legacy | `4885c9771a53ad1adc2c0bffaff738e4aed3d0de434f9a39a17cba1fdba6204d` | `freeze/confirmation_set_proposed.json` (**preserved**) |
| **v1 canonical** | `1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4` | `freeze/confirmation_set_v1_proposed.json` |

Membership unchanged; hash change is serialization only. Expected hashes in tests are **documented constants**, not auto-rewritten.

Regression tests cover: stable hash, question change, answer change, task-order independence (sort by id), declared-hash tamper, expected-hash mismatch, missing field, non-str field, duplicate id.

### Task D — Statistics input validation

| Fix | Behavior |
|---|---|
| `count_paired` types | only `bool` (optional `allow_int_01=True` for 0/1). **`"false"` / `"true"` / `None` / floats raise `TypeError`** — string `"false"` is never "correct" |
| Missing results | raise `ValueError` / `TypeError`; never coerced to wrong; never dropped from denominator |
| Duplicate explicit IDs | `ValueError` |
| ID set mismatch | `ValueError` |
| McNemar one-sided direction | pre-declared `direction="comparator_better"|"baseline_better"`; `comparator_better` uses P[X≥b]; sign of (b−c) cannot silently flip the tail |
| Negative / bool counts | rejected |

---

## 3. Decisions required from Planner

| ID | Decision | Executor recommendation |
|---|---|---|
| **D1** | Accept PREREGISTRATION after D/E redesign | Accept as v1; freeze U1–U5 before any call |
| **D2** | Accept **v1** confirmation freeze (`1771a67c…`) | Accept; keep v0 for audit |
| **D3** | Unblock official GSM8K **train** for generation/dev | **Required** for D/E |
| **D4** | Or approve labeled test-split policy deviation | Default **reject** |
| **D5** | New request authorization | Full A–E = **480** calls; remaining **56**; gap **424** |
| **D6** | Fund/implement AFlow-Parent→mutable-genome adapter for Group E | Without it, E is `BLOCKED_IMPLEMENTATION` — do not relabel D as E |
| **D7** | Optional: exclude index 13 (protocol reservation) before accept | Not required for scoring independence; optional hygiene |

---

## 4. Budget recap (unchanged totals, clarified structure)

| Group | Requests | Notes |
|---|---:|---|
| A | 40 | 1-shot |
| B | 120 | k=3 |
| C | 80 | fixed verify |
| D | 120 | 4×20 dev + 40 conf |
| E | 120 | (2×20 + 2×20) dev + 40 conf — **matched with D** |
| **Total** | **480** | remaining 56 → **gap 424** |

Cost remains non-binding (~$1–1.5 worst-case vs ~$4.96 left). Token-out high bound risk at 480×800 still noted.

---

## 5. Execution record

| Field | Value |
|---|---|
| New real API / HTTP model requests | **0** |
| Authorization | read-only; 244 attempts; $0.0363972 spent; not blocked |
| Frozen results | 402 files, 0 modified vs `766a610` |
| R3 hash gate | not modified, not bypassed |
| v0 freeze file | unchanged |
| Silent mock / auto-hash rebuild | none |
| Full suite | **962 passed / 0 failed / 2 skipped / RETCODE 0** |
| Targeted suite | **126 passed / 0 failed / 0 skipped / RETCODE 0** |

---

## 6. Stop statement

`LEVEL3-PILOT-R4-DESIGN-REVIEW-FIX` is complete and **STOPPED**. No real experiment started. No budget increased. No preregistration finalized. No confirmation set marked accepted-frozen. Executor awaits Planner independent review and explicit user authorization.

