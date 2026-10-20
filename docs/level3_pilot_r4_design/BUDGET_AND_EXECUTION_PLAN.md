# LEVEL3-PILOT-R4 — Budget and Execution Plan

**Status:** DESIGN PREP — estimation only. **Zero real model requests were issued to produce this document.**
**Baseline commit:** `eaca0b87071fa1387d5bd76a045ce247b568ba65`.
**Authorization state (read-only):** see section 2. Nothing in this round modified the ledger.

> **Terminology.** Every USD figure below is an **internal usage estimate or a settled ledger figure**. None of them is a provider invoice. `PROVIDER_INVOICE = NOT_VERIFIED`.

---

## 1. Scope of the planned study (R4 A-E)

Operational definitions are in `PREREGISTRATION.md`. This document only prices them.

Parameters used in the tables (defaults proposed by Executor; Planner may change **before** freeze):

| Parameter | Symbol | Default |
|---|---|---:|
| Confirmation tasks | `n_conf` | 40 |
| Samples per task (Group B) | `k` | 3 |
| Candidates per run (Group D/E) | `m` | 4 |
| Development tasks for candidate ranking | `s` | 20 |
| Model | — | `deepseek-flash` (same as R3) |

---

## 2. Current authorization state (READ-ONLY snapshot)

Source: `~/.evopareto/state/level3_pilot_authorization.json` (not modified).

| Field | Value |
|---|---|
| `auth_id` | `level3-pilot-authorization-v1` |
| Cap: max physical requests | **300** |
| Cap: max cost USD | **5.00** |
| Cap: max tokens in / out | 2,000,000 / 200,000 |
| Consumed: physical_attempts | **244** |
| Consumed: spent_cost_usd | **0.0363972** (settled) |
| Consumed: actual tokens in / out | 10,622 / 27,605 |
| Outstanding reserved | 0 |
| Unknown usage | 0 |
| `blocked` | false |
| **Remaining physical requests** | **56** |
| **Remaining cost USD** | **≈ 4.9636** |
| Provider invoice | **NOT_VERIFIED** |

**Prohibited recovery methods (frozen):** changing Run ID, deleting the SQLite/JSON ledger, changing the DB path, rewriting the authorization record, or any other reset. Quota is only extended by an explicit new Planner/user authorization.

---

## 3. Request-count budget by group

### 3.1 Formula

| Group | Confirmation calls | Generation/selection calls | Total |
|---|---|---|---|
| **A** Parent | `n_conf × 1` | 0 | `40` |
| **B** Sampling Control | `n_conf × k` | 0 | `120` |
| **C** Fixed Modification | `n_conf × 2` | 0 | `80` |
| **D** Random Mutation | `n_conf × 1` | `m × s` dev evaluations (+ `D_mut` mutation calls) | `120` |
| **E** Evolutionary Selection | `n_conf × 1` | `m × s` dev evaluations (+ `E_mut` mutation calls) | `120` |
| **Total (A–E)** | | | **480** |

With the defaults: `n_conf=40`, `k=3`, `m=4`, `s=20`, and syntactic-only mutation (`D_mut=E_mut=0`):

| Group | Breakdown | Requests |
|---|---|---:|
| A | 40 × 1 | **40** |
| B | 40 × 3 | **120** |
| C | 40 × 2 | **80** |
| D | 4×20 dev + 40 conf | **120** |
| E | 4×20 dev + 40 conf | **120** |
| **Grand total** | | **480** |

### 3.2 What is NOT counted here (must be added if Planner chooses those options)

- LLM-based mutation/rewrite for D or E (would add `m` or more calls per run).
- Group "Child replica" external reference (U6 in preregistration).
- Retry calls beyond the frozen retry policy (retries still debit the ledger).
- Multi-generation evolution (`g > 1`): multiply dev-eval block by `g`.

---

## 4. Token and cost estimates

### 4.1 Unit rates (from existing evidence)

| Basis | Unit cost / request | Provenance |
|---|---:|---|
| R3 parent settled | ≈ $0.000158 | `0.0055302 / 35` |
| R3 child settled | ≈ $0.000147 | `0.0154032 / 105` |
| R3 prereg worst-case | ≈ $0.003000 | `0.525 / 175` in `paired_confirmation_set_35.json.budget_precheck` |

Historical aggregate token mix (all stages to date, 244 attempts): **10,622 in / 27,605 out**. Per-attempt averages are low because many calls were short; R4 tasks may be longer.

### 4.2 Token planning bounds (conservative)

| Stream | Low estimate / request | High estimate / request | Rationale |
|---|---:|---:|---|
| Input tokens | 150 | 400 | question + system/instruction |
| Output tokens | 150 | 800 | step-by-step reasoning + answer |

At `480` requests: **input ≈ 72,000–192,000**, **output ≈ 72,000–384,000**.  
Compare caps: in ≤ 2,000,000 (OK), out ≤ 200,000 (**output high bound 384,000 exceeds the 200k token-out cap** if every request produced 800 output tokens).

**Conservative action:** budget assumes median output ~300 tokens → ~144,000 output tokens, which fits the 200k cap with margin only if `grand` stays near 480. A longer-output model setting would require either a smaller study or a higher token cap.

### 4.3 Cost estimates (estimate only — not a vendor bill)

| Basis | Unit | Total for 480 requests |
|---|---:|---:|
| R3 parent settled rate | $0.000158 | **≈ $0.0758** |
| R3 child settled rate | $0.000147 | **≈ $0.0704** |
| R3 worst-case rate | $0.003000 | **≈ $1.4400** |

Against remaining cost cap **≈ $4.9636**: cost is **not** the binding constraint. **Physical request count is.**

---

## 5. Latency and success-rate accounting

### 5.1 Latency

| Measure | How recorded | R3 reference |
|---|---|---|
| Per-task end-to-end `latency_s` | already in per-task records | R3 parent/child ≈ 5.3–5.5 s on Docker runs |
| Per-group median / p90 | computed offline from per-task rows | to be reported in R4 results |
| Serial vs parallel | B's `k` samples may run concurrently; wall-clock ≠ sum of latencies | report both `sum(latency_s)` and wall-clock |

Planning note: 40 tasks × 5 s ≈ 200 s serial per 1-call arm; Group B at k=3 is 3× calls but may share wall-clock if parallelized.

### 5.2 Success taxonomy (mandatory columns)

| Category | Counts toward accuracy denominator? | Tracked separately? |
|---|---|---|
| `correct` | yes (=1) | yes |
| `incorrect` (valid output, wrong gold) | yes (=0) | yes |
| `invalid_output` (unparseable) | yes (=0) | yes |
| `timeout` | yes (=0) | yes |
| `execution_failure` (Docker/IPC/HTTP) | yes (=0) | yes |
| `missing` (no row) | yes (=0) | yes + completeness alarm |

**No row may be deleted from the denominator to improve a success rate.**

---

## 6. Authorization gate (pre-execution checklist)

Before **any** real request under R4:

1. Planner accepts `PREREGISTRATION.md`.
2. Planner accepts the confirmation freeze (and unblocks generation/dev, or approves a labeled policy deviation).
3. Task-set hash gate passes with the accepted SHA.
4. A **new authorization** is granted covering the full planned request count (see gap below).
5. Ledger precheck confirms remaining requests ≥ planned + safety margin.
6. `PROVIDER_INVOICE` remains `NOT_VERIFIED` in all reports unless a real bill is attached.

If any gate fails: **stop**. Do not issue partial "just to try" calls.

---

## 7. Budget gap (must not be silently truncated)

| Item | Requests |
|---|---:|
| Planned A–E grand total (defaults) | **480** |
| Remaining under current authorization | **56** |
| **Gap** | **424** |

| Item | USD |
|---|---:|
| Worst-case cost estimate | ≈ $1.4400 |
| Remaining cost authorization | ≈ $4.9636 |
| Cost gap | ≈ $0.0000 (not binding) |

### 7.1 Options for Planner (Executor will not choose)

| Option | Request need | Study integrity | Notes |
|---|---:|---|---|
| **O1.** New authorization for full A–E at `n_conf=40` | ≥ 480 + 10% margin | Full preregistration executable | preferred for RQ1–RQ4 |
| **O2.** Reduce `n_conf` to fit 56 requests | ≤ 56 | Only a strict subset of contrasts; wide CIs; must label `INCOMPLETE` | not recommended as confirmatory |
| **O3.** Run only A vs B first (isolate sampling) | 40 + 120 = 160 | Still needs new authorization | addresses RQ2 only |
| **O4.** Freeze design now; execute after train split + budget approval | 0 now | Keeps evidence clean | **this round's implicit path** |

**Gap must be reported and authorized explicitly. The Executor will not shrink the study silently, and will not issue requests to "see if it works".**

---

## 8. Ledger and audit obligations during execution

| Obligation | Mechanism (existing) |
|---|---|
| Request debit before call | `src/runtime/auth_ledger.py` RESERVED state |
| Settlement after call | `settled_actual` / `settled_unknown_blocked` |
| Cross-process lock | OS file lock on `level3_pilot_authorization.json` |
| Fail-closed | `PERSIST_FAULT` marker; blocked=true refuses new work |
| No quota restore | state machine + tests in `test_hard_budget.py`, `test_l3r2_budget_persistence.py` |
| Frozen results immutable | `tests/frozen_guard.py` (402 tracked files) |
| Cost reconciliation | report both usage estimate and settled actual; invoice stays `NOT_VERIFIED` |

---

## 9. Explicit non-actions of this round

| Action | Done? |
|---|---|
| Real API / HTTP model requests | **0** |
| Budget increase / authorization reset | **NO** |
| Ledger rewrite | **NO** |
| R3 task-set or result modification | **NO** |
| NSGA-III experiment start | **NO** |
| Calling synthetic data "official GSM8K" | **NO** |

---

## 10. Summary numbers (copy-ready)

```
PLANNED_REQUESTS_FULL_AE = 480
REMAINING_REQUESTS_NOW   = 56
REQUEST_GAP              = 424
PLANNED_COST_WORST_EST   = $1.4400   # estimate, not invoice
REMAINING_COST_AUTH      = $4.9636
PROVIDER_INVOICE         = NOT_VERIFIED
NEW_REAL_REQUESTS_THIS_ROUND = 0
```

