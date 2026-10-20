# LEVEL3-PILOT-R4 — Experiment Preregistration

**Status:** DRAFT — DESIGN PREP ONLY. No real model calls have been made under this document.
**Freeze authority:** Planner must accept this document (and the task-set freeze in `TASKSET_AND_STATISTICS.md`) **before** any new real API request.
**Evidence class of this document:** OFFLINE_DESIGN.
**Baseline commit:** `eaca0b87071fa1387d5bd76a045ce247b568ba65`.
**Relation to prior work:** independent EvoPareto-Agent Level 3 Pilot study. Not part of any master's thesis / NSGA-III project.

---

## 0. What this experiment is for

R3 compared a frozen Parent workflow against an Optimizer-produced Child workflow on 35 synthetic GSM8K-style tasks and observed Parent 29/35 vs Child 31/35 (net +2; McNemar two-sided p = 0.50). That contrast is **confounded**: the Child also spends 3–4 inference calls per task versus the Parent's 1 call. R3 therefore cannot say whether any gain comes from workflow structure, from extra sampling, or from evolutionary selection.

R4 is designed to **decompose** those contributions. It is a preparation-stage document: success is an auditable, falsifiable protocol — **not** a positive result.

---

## 1. Research questions (fixed; not editable by Executor)

**RQ1.** Does workflow improvement raise task accuracy **stably on an independent confirmation set**?

**RQ2.** Can any gain be explained by extra sampling, answer format, or a fixed modification alone?

**RQ3.** Does evolutionary selection contribute **beyond** random mutation and fixed modification?

**RQ4.** If accuracy improves, how many extra calls, tokens, latency, and dollars does the improvement cost?

These four questions are the contract. If a control cannot be run under a fair budget, it is marked **UNRESOLVED** and retained — it is not deleted.

---

## 2. Hypotheses and falsifiability

Primary accuracy is measured only on the **confirmation set** (official GSM8K test split, frozen under `TASKSET_AND_STATISTICS.md`).

| ID | Hypothesis | Falsified / rejected if |
|---|---|---|
| H1 | Some improved workflow (C, D, or E) beats frozen Parent (A) on confirmation accuracy | All of C,D,E ≤ A on confirmation, or the only gains vanish at matched call budget |
| H2a | Sampling alone (B) explains a substantial share of any A→Child-type gain | B ≈ A (difference ≈ 0 within CI) while C/D/E still beat A |
| H2b | A single fixed modification (C) explains gains attributed to "evolution" | C ≥ D and C ≥ E on confirmation |
| H3 | Evolutionary selection (E) beats random mutation (D) and fixed modification (C) | E ≤ D and E ≤ C on confirmation under equal candidate-evaluation budget |
| H4 | Accuracy gains are bought with measurable extra calls/tokens/latency/cost | Reported cost/call deltas are not consistent with recorded ledgers (analysis failure) — or gains require disproportionately more budget (report as tradeoff, not as failure) |

**Direction convention.** All confirmatory tests are **two-sided** unless a one-sided test is frozen here before data collection. This document freezes **two-sided α = 0.05**. One-sided p-values may appear as descriptive supplements only.

**Strong negative claim protection.** If E does not beat D, the correct conclusion is "no evidence that evolutionary selection beats random mutation at this budget and N", **not** "evolution is impossible".

---

## 3. Experimental groups — operational definitions

Every group is defined by **executable operations** (what is called, how many times, how answers are reduced). A group name is not evidence that an algorithm exists.

Shared constants (frozen at execution time by the accepted freeze file):

| Symbol | Meaning | Proposed default (needs Planner freeze) |
|---|---|---|
| `k` | samples per task for aggregation arms | **3** (matches R3 child scale) |
| `m` | candidate workflows generated per run (D/E) | **4** |
| `s` | development-set tasks used to rank/select candidates | **20** (official train split) |
| `n_conf` | confirmation tasks | **40** (official test split; see freeze doc) |
| `n_gen` | generation tasks (candidate production) | **N/A** — R4 mutations are fixed syntactic operators (`MutationPlan`); no separate generation-task set is consumed. Dev ranking uses `s` only. |
| Model | same provider/model for all groups | `deepseek-flash` |
| Scoring | host-side gold; never in container/prompt/IPC | as R3 |

### Group A — Parent (frozen baseline)

- Workflow: the frozen `parent_graph.py` (SHA `ee6cde43...`) and `parent_prompt.py`.
- Calls per task: **1**.
- Answer extraction: existing project extractor.
- Role: absolute baseline. Never modified.

### Group B — Sampling Control

- Workflow source, instruction text, and prompt contract: **identical to Group A**.
- Calls per task: **k = 3** independent completions of the **same** A request (temperature/default as A).
- Aggregation: majority vote over extracted answers; ties broken by lowest-index sample (rule frozen here).
- Purpose: price the "extra sampling" confound. **No structural change, no evolved instruction.**
- If B alone reproduces the R3 Child-scale gain, RQ2 answers "sampling suffices".

### Group C — Fixed Modification

- A single **pre-specified** workflow edit, chosen **before** any new model call, not selected by search.
- Proposed default (Planner may replace **before** freeze, not after):
  - Keep A's single Custom call, then one **fixed** verification pass with a hard-coded checker instruction ("Recompute the arithmetic and output the final number only."),
  - Calls per task: **2**,
  - Answer: the checker's extracted answer.
- No candidate search, no selection, no mutation.
- Purpose: upper-bound a "hand-designed structural change" at modest extra cost.

### Group D — Random Search (flat, no lineage)

*Independence rule:* every candidate is generated **from the frozen Parent only**. No candidate may be generated from another candidate.

Operational definition (frozen):

1. Start from frozen Parent graph/prompt (Group A artefacts).
2. Produce exactly **4** random mutation candidates (`cand_d1 … cand_d4`) by applying seeded random edits to the Parent. RNG seed frozen before calls.
3. Evaluate **each** candidate on the **same development set** (`s` tasks).
4. Select the candidate with the **highest development accuracy**.
5. Tie-break: **pre-frozen candidate order** (`cand_d1` < `cand_d2` < `cand_d3` < `cand_d4`), i.e. lowest index wins.
6. Confirmation: run **only the selected candidate** on the shared confirmation set.
7. Candidate generation must not read confirmation questions' labels or confirmation accuracy.

Failure rule: a candidate that fails to produce a valid workflow is scored as dev-accuracy 0 and **stays in the candidate list** (it can still lose selection; it is not deleted to tidy the race).

Purpose: price "random search over edits" at a fixed candidate budget, **without** inter-candidate lineage.

### Group E — Two-Generation Evolution (lineage, matched budget)

Operational definition (frozen):

1. **Generation 1:** from frozen Parent, produce **2** mutated candidates (`e1a`, `e1b`) with the same operator distribution as Group D, **seeded independently of D's seed** (or, if a paired seed is used, it must be declared in the freeze file).
2. Evaluate `e1a`, `e1b` on the **same development set** used by Group D.
3. **Gen-1 winner** = higher dev accuracy; tie → frozen order (`e1a` before `e1b`).
4. **Generation 2:** from the **gen-1 winner only** (not from Parent, not from the gen-1 loser), produce **2** further mutants (`e2a`, `e2b`).
5. Evaluate `e2a`, `e2b` on the **same development set**.
6. **Final selection among all 4 candidates** `{e1a, e1b, e2a, e2b}` by dev accuracy; tie → frozen order `e1a < e1b < e2a < e2b`.
7. Confirmation: run **only the final winner** on the shared confirmation set.

Identifiability contract (D vs E):

| Dimension | Group D | Group E | Must match? |
|---|---|---|---|
| Total candidates | 4 | 4 | **YES** |
| Dev-eval calls | 4 × `s` | 4 × `s` | **YES** |
| Confirmation calls | 1 × `n_conf` | 1 × `n_conf` | **YES** |
| Mutation operator distribution | frozen | frozen | **YES** |
| Confirmation tasks | shared | shared | **YES** |
| Parent of gen-1 mutants | frozen Parent | frozen Parent | **YES** |
| Parent of later mutants | n/a (all from Parent) | **gen-1 winner** | **NO — this is the only intended difference** |
| Access to confirmation labels | forbidden | forbidden | **YES** |

The contrast E−D is therefore: *does mutating from a selected ancestor beat mutating from the same root, at equal candidate and evaluation budget?*

**This is NOT a claim of recursive self-improvement.** Two generations is a bounded lineage ablation. Open-ended RSI is not tested and must not be reported as achieved.

### Mutation implementation feasibility (R4-R2 status)

| Item | Status | Evidence |
|---|---|---|
| `WorkflowGenome` (fceol) usable for R4? | **NO** | Different execution engine (`fceol.offline_evaluator`), no Docker/DeepSeek IPC, no AFlow `Custom` |
| `AgentGenome` usable for R4? | **NO** | Categorical agent config, not an executable workflow |
| Frozen Parent adapter | **IMPLEMENTED** | `src/research/r4_workflow_program.py` — `load_frozen_parent` with SHA gates; unmutated program **identity-compiles** to frozen `parent_graph.py` |
| Mutations | `M_SET_INSTRUCTION`, `M_ADD_SAMPLING`, `M_ADD_CHECK_STAGE`, `M_SINGLE_EDIT` | clone-and-edit, syntactic, no model calls |
| Group D lineage | **IMPLEMENTED** | `generate_flat_candidates` — all 4 from frozen Parent; violation raises `LINEAGE_FLAT_VIOLATION` |
| Group E lineage | **IMPLEMENTED** | `generate_two_generation_candidates` — gen2 must descend from gen-1 winner |
| Offline tests | 30 adapter tests pass | `tests/baseline_first/test_r4_parent_adapter.py` (SIMULATED local execution; selection; Group C; lineage) |
| Local mock execution | **READY** | `execute_program_locally` (SIMULATED hook; answer extraction; ctor probes) |
| Real Docker/DeepSeek candidate eval | **NOT RUN** | still authorization-gated (see `RQ3_MULTI_SEED_DESIGN.md`) |
| Group C fixed-verify | **IMPLEMENTED** | `build_group_c_fixed_verify` (Parent call + one fixed verify, 2 calls) |
| Algorithm-level claim (RQ3) | **NOT SUPPORTED at R=1** | see multi-seed design: `TOTAL_REQUESTS(R)=240+240R` |

**Status layers (do not conflate):**  
1. **Representation layer — READY:** `WorkflowProgram`, hashes, lineage, selection, Group C.  
2. **Execution layer (local mock) — READY:** SIMULATED IPC hook, answer extraction, error paths.  
3. **Execution layer (Docker + real model) — NOT RUN:** authorization-gated.  
4. **Formal experiment / final freeze — NOT APPROVED.**  
**Recursive self-improvement:** still **NOT** claimed. Two-generation lineage ≠ open-ended RSI.

### Search-seed design (RQ3)

Plan P (R=1) is **exploratory candidate comparison only**.  
Plan C (R=5 or 10) is required for algorithm-level claims.  
Full budget and statistical plan: `RQ3_MULTI_SEED_DESIGN.md`.  
Formula: `TOTAL_REQUESTS = 240 + 240*R`.

### Shared frozen parameters (D/E)

| Symbol | Meaning | Proposed default |
|---|---|---:|
| `m` | candidates per group (total) | **4** |
| `s` | development-set size (train split) | **20** |
| `n_conf` | confirmation-set size | **40** (v1 freeze) |
| seed_D | RNG for Group D | freeze file |
| seed_E | RNG for Group E | freeze file |
| tie order | candidate creation order | `cand_d1..4` / `e1a,e1b,e2a,e2b` |
| failed candidate | dev score | **0**, retained |

### Budget-matched secondary contrast (pre-specified)

For every pair (X, Y) where call counts differ, the report **must** also present a **budget-matched** view: either (i) truncate to the smaller per-task call budget by subsampling samples/candidates with the frozen seed, or (ii) report accuracy-vs-calls Pareto points. The primary analysis is at native group definition; the budget-matched view is secondary but mandatory. **Silently comparing unequal budgets is prohibited.**

---

## 4. Data roles (strict separation)

| Role | Split | Used for | Used for final claims? |
|---|---|---|---|
| **Generation** | official GSM8K **train** | producing candidates (D/E) | NO |
| **Development / selection** | official GSM8K **train** (verified 7473 rows) | ranking/selecting candidates (D/E) on `s=20` tasks | NO |
| **Generation tasks** | **not required** | mutations are fixed syntactic operators from `MutationPlan` (no LLM rewrite) | NO |
| **Confirmation** | official GSM8K **test** | final scoring for **all** groups A–E | YES |
| **Calibration / dry-run** | offline fixture or mock only | plumbing tests | NO |

Rules frozen here:

1. Confirmation tasks are identical for all groups.
2. Evolutionary / random selection **never** sees confirmation labels or confirmation accuracy.
3. Official test split is **never** used for mutation, selection, or early stopping.
4. Any task used to design a group (e.g., manual smoke tests) is excluded from confirmation by ID, with the exclusion list frozen before sampling (same discipline as R3's 12-id exclusion).
5. Mock or simulated data may never enter confirmatory statistics. If produced, it must be tagged `evidence_class: SIMULATED` and stored outside the real-results namespace.

---

## 5. Freeze commitments (before any new real call)

The following must be written to a freeze file and hash-checked at run start (same style as `run_paired_35.verify_taskset`):

1. Full confirmation task list (id, question, gold, source index) + SHA-256 of the canonical task tuple list.
2. Generation and development task lists + hashes.
3. Group A/B/C source hashes (graph, prompt, bundle).
4. Group D mutation operator list + RNG seed.
5. Group E selection mechanism parameters (μ, generations, survivor rule, tie-break).
6. Scoring function version / extractor version.
7. Exclusion list.
8. Required request count and worst-case cost (from `BUDGET_AND_EXECUTION_PLAN.md`).
9. Statistical analysis plan version = this file's section 6.

**After freeze:** any change creates a **new version** of this document and requires Planner re-approval. No post-hoc replacement of metrics or tests.

---

## 6. Outcomes, statistics, and stopping rules (frozen)

### 6.1 Outcomes

| Outcome | Definition | Role |
|---|---|---|
| `correct` | extracted answer equals gold (project extractor) | **primary** |
| `invalid_output` | extraction failed / empty / non-parseable | counts as **incorrect** in primary; tracked separately |
| `timeout` / `execution_failure` | container/IPC/HTTP failure after retry policy | counts as **incorrect** in primary; tracked separately |
| `calls`, `tokens_in`, `tokens_out`, `latency_s`, `cost_usd` | from ledger | RQ4 |

**All failures remain in the denominator.** Removing failed tasks to raise accuracy is prohibited.

### 6.2 Paired comparison structure

On the confirmation set, for each pair (Baseline A, Comparator X ∈ {B,C,D,E}):

| Cell | Count symbol |
|---|---|
| X correct, A wrong | `b` (improved) |
| X wrong, A correct | `c` (regressed) |
| both correct | `n11` |
| both wrong | `n00` |

Primary test: **exact McNemar**, two-sided, on discordant pairs `b,c`.

Also reported for every group: accuracy, Wilson 95% CI for accuracy, paired risk difference (b−c)/n with bootstrap or Newcombe paired CI.

### 6.3 Multiplicity

Four primary contrasts vs A: B−A, C−A, D−A, E−A.
Plus the RQ3-specific contrast: **E−D** (and E−C as secondary).

Holm–Bonferroni family-wise correction at α = 0.05 over the **family of five** listed above. Unadjusted p-values also reported. No switching to uncorrected tests after seeing data.

### 6.4 Stopping rules

- **Fixed-N design.** Run exactly the frozen `n_conf` confirmation tasks for every group. No optional stopping, no "stop when significant".
- If a hard safety failure occurs (budget cap, auth block, data corruption), run **aborts**, partial data is preserved and labeled `ABORTED_PARTIAL`, and is **not** used for confirmatory claims.
- If quota is insufficient for all groups, the study is reported as **INCOMPLETE** with the executed subset clearly labeled; no re-scoping of hypotheses.

### 6.5 Sample-size stance (no convenience N)

A sample size is **not** chosen to manufacture significance. Estimation method and ranges are in `TASKSET_AND_STATISTICS.md`. The frozen `n_conf` must be justified from assumptions, and the report must state the detectable effect at that N.

---

## 7. Analysis commitments for RQ4 (cost)

For every group report, with ledger provenance:

- total physical HTTP requests,
- requests per task (mean and distribution),
- tokens in/out (settled),
- end-to-end latency per task (median, p90),
- cost estimate vs `SETTLED_ACTUAL` (provider invoice still `NOT_VERIFIED`),
- success taxonomy counts (correct / incorrect / invalid / timeout / execution_failure).

Efficiency view: accuracy vs requests, accuracy vs USD, accuracy vs latency. A gain that needs 3× calls must be reported as a 3× budget result, not as a pure algorithmic win.

---

## 8. What R4 will NOT claim

1. Not "recursive self-improvement achieved" unless a multi-generation loop was actually run and beat controls — default design is single-generation.
2. Not "official GSM8K SOTA" — this is a controlled ablation at micro budget on one model.
3. Not "evolution works" from a single positive contrast; RQ3 specifically requires E > D and E > C.
4. Not causal claims from correlational cost–accuracy curves.
5. Mock success is never real success.

---

## 9. Unresolved parameters (must be decided by Planner before freeze)

| # | Parameter | Status | Why unresolved |
|---|---|---|---|
| U1 | `n_conf` confirmation size | PROPOSED 40 | Depends on remaining/new quota and detectable effect; see sample-size ranges |
| U2 | `k` samples for Group B | PROPOSED 3 | Must match a fair budget story vs C/D/E call counts |
| U3 | Group C exact fixed modification | PROPOSED "add one verify pass" | Planner may choose a different fixed edit; must be frozen before calls |
| U4 | Group D mutation operator set | PROPOSED use existing fceol/evolution operators, syntactic-only first | If LLM-rewrite mutations are included, cost explodes. Same operator distribution required for D and E |
| U5 | Group E selection mechanism | **IMPLEMENTED**: two-generation lineage (2+2) via `generate_two_generation_candidates`; final pick among 4 on shared dev scores with creation-order ties (`select_e_final`) | Real-model scoring still authorization-gated; RQ3 algorithm-level claim needs R≥6 paired seeds (see `RQ3_MULTI_SEED_DESIGN.md`) |
| U6 | Whether to include a "Child replica" group (exact R3 child) as external reference | OPEN | Useful benchmark but costs calls; R3 child already characterized |
| U7 | New budget authorization amount | OPEN | Current remaining quota is only 56 requests — insufficient for A–E (see budget doc) |
| U8 | Task-set freeze acceptance | PROPOSED in freeze doc | Planner must accept before sampling |

**Rule:** if any of U1–U5 remains open at execution time, the corresponding contrast is labeled **UNRESOLVED**, not dropped.

---

## 10. Sign-off checklist (Executor completed; Planner to approve)

- [x] Baseline audit recorded (`BASELINE_AUDIT.md`)
- [x] Groups A–E operationally defined
- [x] RQ1–RQ4 retained without deletion of awkward controls
- [x] Data roles separated (train vs test)
- [x] Primary metric, paired test, multiplicity, stopping rule fixed
- [x] Failure retention rule fixed
- [x] Cost accounting committed
- [x] Unresolved parameters listed explicitly
- [ ] **Planner acceptance of this document**
- [ ] **Planner acceptance of task-set freeze**
- [ ] **Planner authorization of any new real-model budget**

Until the last three boxes are checked by Planner/user, **zero** real model requests may be issued.

