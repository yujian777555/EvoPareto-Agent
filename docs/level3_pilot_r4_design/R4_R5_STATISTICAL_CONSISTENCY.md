# R4-R5 Statistical Protocol Consistency

**Status:** PROPOSED freeze status; **F2 method decided (IUT)** by Planner — still not an execution approval. Zero real model results this round.  
**Files unified:** `PREREGISTRATION.md`, `TASKSET_AND_STATISTICS.md`, `RQ3_MULTI_SEED_DESIGN.md`, `RQ3_POWER_TABLES.txt`, `BUDGET_AND_EXECUTION_PLAN.md`, `execution_freeze_v1_proposed.json`, `src/research/r4_exec_freeze.py`.

---

## 1. Conflict resolved (D1)

| Source | Old statement | Unified statement |
|---|---|---|
| R4-R4 handoff / RQ3 §6.0 | Seed-level E−D = family F2 alone; Holm(5) is task-level only | **Kept as the base rule** |
| `execution_freeze_v0` holm_note | Could be read as putting seed E−D into Holm(5) | **v1 freeze** now says: F1 Holm(5) = **task-level only**; seed-level RQ3 = **F2** |
| Docs vs verifier | verifier required holm_family length 5 without saying what layer | verifier now also requires `rq3_comparisons` with E−D and E−C roles |

**Rule:** never apply Holm(5) first-step (0.01) to the seed-level Wilcoxon. Never claim seed-level significance from task-level Holm output.

---

## 2. RQ3 comparisons: E−D and E−C (D2)

Research question: *does evolutionary selection beat random search **and** fixed modification?*

| Comparison | Meaning | Role | Family |
|---|---|---|---|
| **E − D** | two-generation lineage vs flat random search | **co-primary** | F2 |
| **E − C** | two-generation lineage vs fixed verify modification | **co-primary** | F2 |

**Claim rule (frozen for this proposal):**  
RQ3 “E beats the search/fixed baselines” requires **both** E−D and E−C to reject in favor of E at their pre-declared F2 threshold. A hit on E−D alone supports only “E beats random search”, not “E beats fixed modification”.

### F2 multiplicity — **DECIDED: IUT** (Planner)

| Item | Rule |
|---|---|
| Family | F2 = {E−D, E−C} |
| Test | exact two-sided Wilcoxon signed-rank per contrast, α=0.05, direction must favor E |
| Multiplicity | **IUT only** — joint claim requires **both** contrasts to reject in favor of E |
| Holm(2) | **NOT used on F2** |
| Single-contrast confirmatory claims | require a pre-declared FWER control; otherwise **exploratory/descriptive only** |

**Claim rule:** “E simultaneously beats D and C” holds iff both E−D and E−C reject favoring E at α=0.05.  
A hit on E−D alone supports only “E beats random search”, not the joint claim.

**R=6 is necessary, not sufficient:** exact two-sided Wilcoxon min p uses the number of **nonzero** paired differences `n_eff`, not nominal R. Report `n_eff`, zeros, ties, and attainable min p.

## 3. Consistency table (D3)

| Item | Unified specification |
|---|---|
| **Null hypotheses** | (Task F1) each of B,C,D,E equals A on confirmation accuracy; E equals D (task-level). (Seed F2) E−D ≤ 0; E−C ≤ 0 across blocks |
| **Primary endpoints** | Seed-level `acc_E−acc_D` and `acc_E−acc_C` on the **frozen 40 tasks** (conditional) |
| **Secondary** | Task-level Holm(5) F1; per-block McNemar; cost/calls; B/C/D vs A |
| **Test methods** | Task: exact McNemar two-sided. Seed: exact Wilcoxon signed-rank two-sided on paired `d[r]` (drop zeros) |
| **Multiplicity** | F1 Holm(5) task-level only. F2 = {E−D, E−C} per option F2-a/b/c above |
| **Sample size** | Fixed R ∈ {6,10} declared before data; n_conf=40 fixed |
| **Failed seeds** | Primary: method–seed accuracy = 0.0, denominator kept. Sensitivity: complete-case |
| **Zero / tied differences** | Zeros dropped from Wilcoxon (report n_nonzero); ties in \|d\| → average ranks; sign test sensitivity |
| **Confidence intervals** | Wilson for proportions; bootstrap over blocks (10k, seed frozen) for mean d[r] |
| **Stopping** | Fixed-N only; no optional stopping; no method switch after outcomes |
| **Power claims** | Exact p_min tables + normal-approx R only. **No** simulated power claimed unless a simulation is actually run |
| **Generalization** | Seed tests are **conditional on the frozen 40 tasks**. GSM8K-distribution claims need pre-specified crossed task×seed model |

### What this can and cannot support

| Claim | Supported? |
|---|---|
| “On this confirmation set, under these seeds, E’s candidate beat D’s / C’s” (Plan P or per-block) | YES, exploratory / per-block |
| “Evolutionary selection stably beats random search” (E−D seed-level) | YES **if** F2 test rejects at pre-declared threshold and R≥6 (or ≥7 under Holm(2)) |
| “Evolutionary selection stably beats fixed modification” (E−C) | YES **if** that test rejects |
| “E beats both D and C” | YES **only if** both E−D and E−C pass (IUT / Holm(2)) |
| “Evolution works on GSM8K distribution” | **NO** (conditional on 40 tasks) |
| “Recursive self-improvement proven” | **NO** |
| R=5 algorithm-level significance | **NO** (exact two-sided min p=0.0625) |

---

## 4. Remaining Planner decisions

1. Choose F2-a / F2-b / F2-c.  
2. Confirm co-primary wording in PREREGISTRATION.md.  
3. Accept R=6 vs R=10 (budget: R=6 already exceeds request cap).  
4. Accept execution freeze **v1** (budget gate fail-closed) as the one to freeze later.  
5. Handle legacy `docs/PHASE2_EVOLUTION_MEMORY.md` non-UTF-8 blocking audit independence (exclude explicitly vs re-encode — **not** done this round).

Formal freeze remains **PROPOSED**. No sign-off by Executor.
