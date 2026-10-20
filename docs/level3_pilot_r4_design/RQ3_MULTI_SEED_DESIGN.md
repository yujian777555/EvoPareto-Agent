# RQ3 Multi-Seed Design — Plan P vs Plan C (R4-R3)

**Status:** DESIGN ONLY — zero real model calls. Not an authorization.  
**Baseline commit:** `08af0e6cab458febb94a44d0ca87f5343af4bb78`.  
**Question:** can we claim that two-generation evolution stably beats random search, not merely that one search seed produced a better candidate?

**Companion tables (deterministic script):** `scripts/level3_pilot_r4/rq3_power_tables.py` → `RQ3_POWER_TABLES.txt`.

---

## 1. Why a single search seed is insufficient

| What Plan P (R=1) can say | What it cannot say |
|---|---|
| Under **this** seed, E's selected candidate beat/lost to D's on these 40 tasks | Evolutionary search stably beats random search |
| Pipeline plumbing works | Cross-seed variance σ_d is estimated |
| Exploratory effect size on one draw | Algorithm-level RQ3 |

Search RNG variance is fully confounded with method at R=1. **Plan P does not estimate cross-seed variance** and must not be quoted as if it did.

---

## 2. Seed generation and pairing (frozen)

### 2.1 Independent seeds

For block index `r = 1..R`:

```
plan_seed[r] = BASE_SEED + 1009 * r
```

`BASE_SEED` is written into the execution freeze file (proposed `20260601`, Planner may change **before** any call). Seeds are therefore deterministic and reproducible from the freeze file alone.

### 2.2 Paired blocking (required for Wilcoxon)

D and E in block `r` share the **same** `MutationPlan(seed=plan_seed[r])`:

| Slot | Group D (flat) | Group E (two-generation) |
|---|---|---|
| 0 | mutate **Parent** | mutate **Parent** (same plan draw as D slot 0) |
| 1 | mutate **Parent** | mutate **Parent** (same plan draw as D slot 1) |
| 2 | mutate **Parent** | mutate **gen-1 winner** |
| 3 | mutate **Parent** | mutate **gen-1 winner** |

This is a **valid paired block**: shared mutation randomness on slots 0–1, structural difference only on 2–3 (lineage). Blocks are independent across `r`.

If this pairing is **not** implemented, Wilcoxon signed-rank is **invalid**. Then use an independent-sample method (Mann–Whitney U / permutation test on unpaired seed accuracies) and state the loss of power. **Do not** arbitrarily pair unpaired runs and then apply Wilcoxon.

---

## 3. Exact-test limits at R=5 (critical)

Exact two-sided Wilcoxon signed-rank minimum attainable p-value = `2 / 2^R`:

| R | p_min two-sided | Can reject at α=0.05? |
|---:|---:|---|
| 1 | 1.000 | NO |
| 2 | 0.500 | NO |
| 3 | 0.250 | NO |
| 4 | 0.125 | NO |
| **5** | **0.0625** | **NO** |
| 6 | 0.03125 | YES |
| 10 | 0.001953 | YES |

**R=5 cannot achieve two-sided α=0.05 under the standard exact Wilcoxon (or exact sign test).** Any document that claims otherwise is wrong. At R=5, a two-sided exact test can only be reported as “not significant at 0.05 by construction”; a one-sided exact test can reach 1/32≈0.031, but R4 froze **two-sided** confirmatory tests.

**Minimum R for a possible two-sided exact rejection: 6.** Plan C should target **R≥10** if a significant algorithm-level claim is intended.

---

## 4. Plan P — single-search exploratory pilot

| Item | Value |
|---|---|
| A / B / C | one run each |
| D / E | **one** search seed each (paired block r=1) |
| Confirmation | same 40 tasks |
| Requests | `240 + 240×1 = 480` (+10% margin 528) |
| Allowed label | `SINGLE_SEED_CANDIDATE_COMPARISON_ONLY` |
| Forbidden | algorithm-level claims; σ_d estimation; “evolution is better” |

---

## 5. Plan C — algorithm-level multi-seed comparison

### 5.1 Structure

* A, B, C: one reference run each (not search procedures).
* D and E: **R paired search blocks** each (`R ∈ {6, 10, 20}` recommended; `R=5` reported only as underpowered).
* Per block: same `m=4` candidates, same `s=20` dev tasks, same confirmation set (40 tasks).
* D/E HTTP budget match inside each block (120 vs 120).

### 5.2 Request accounting (margins included)

```
TOTAL_REQUESTS(R) = 240 + 240 * R
WITH_MARGIN(R)    = ceil(1.10 * TOTAL_REQUESTS(R))
```

| R | TOTAL | +10% margin | gap vs 300-cap | worst USD (=$0.003/req) | output tok high (800/req) | output tok med (300/req) |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 480 | 528 | +228 | $1.58 | 422k | 158k |
| 5 | 1,440 | 1,584 | +1,284 | $4.75 | 1.27M | 475k |
| 6 | 1,680 | 1,848 | +1,548 | $5.54 | 1.48M | 554k |
| 10 | 2,640 | 2,904 | +2,604 | $8.71 | 2.32M | 871k |

**Caps (existing authorization, unchanged this round):**

| Cap | R=1 | R=5 | R=6 | R=10 |
|---|---|---|---|---|
| requests ≤ 300 | FAIL | FAIL | FAIL | FAIL |
| output tokens ≤ 200,000 | FAIL at high bound (422k); borderline median (158k) | FAIL | FAIL | FAIL |
| cost ≤ $5.00 | PASS (est.) | PASS (est.) | **FAIL** (est. $5.54) | FAIL |

**No silent reduction.** If authorization cannot cover R, report `INCOMPLETE`.

### 5.3 Token bounds (estimate ≠ invoice)

Per request: input 150–400, output 150–800 (median ~300). R=10 high-bound output ≈ 2.1M–2.3M tokens ≫ 200k cap.

---

## 6. Statistical analysis (Plan C)

### 6.1 Analysis units — do not conflate

| Unit | n | Role |
|---|---:|---|
| Task | 40 | paired correctness within a block |
| Search block (seed) | R | **primary unit for algorithm claims** |
| Task × seed | 40R | descriptive only; **not** i.i.d. Bernoulli |

### 6.2 Primary test (algorithm level)

1. For each block `r`, confirmation accuracy `acc_D[r]`, `acc_E[r]` on the frozen 40 tasks.
2. Differences `d[r] = acc_E[r] − acc_D[r]`.
3. **Primary:** exact two-sided Wilcoxon signed-rank on `d[r]` (paired design §2.2).  
   - If R < 6, the test **cannot** reject at α=0.05; report p and the structural limit.  
   - If pairing (§2.2) is not implemented, switch to **Mann–Whitney U** (independent) and say so.
4. Report mean/median `d`, bootstrap CI over blocks, min/max, and every `d[r]`.

### 6.3 Task dependence (shared 40 confirmation tasks)

* Seed-level `d[r]` are **conditional on this frozen 40-task set**.  
* Claims are of the form: *on this confirmation set, E–D differences across search blocks are…*  
* **Generalization to the GSM8K task distribution is not licensed** by seed-only analysis.

If a distributional claim is required, pre-specify a **crossed** analysis before data:

* hierarchical binomial model: `correct ~ method + (1|task) + (1|seed) + (1|method:seed)`, or  
* two-way bootstrap resampling tasks **and** seeds.

Label such an analysis **secondary / exploratory** unless it was frozen before outcomes.

### 6.4 Failed seeds and failures

| Event | Primary analysis | Sensitivity |
|---|---|---|
| Seed produces only FailedCandidate slots | method–seed accuracy **0.0** (stays in denominator) | complete-case (exclude) reported alongside |
| Confirmation scoring fails for a method–seed | accuracy **0.0** | complete-case |
| HTTP/timeout on a confirmation task | task incorrect, **row kept** | none (no task dropping) |

Never silently drop failed runs.

### 6.5 Secondary per-block McNemar

Within block `r`, McNemar on that block's two selected candidates describes **those candidates**. Holm across blocks if treated as a family. Not the algorithm-level claim.

---

## 7. Power / assumptions (explicit)

### 7.1 Normal approximation (quoted only as approximation)

`R ≈ ((z_{0.975}+z_{0.80}) σ_d / μ_d)^2`

| μ_d | σ_d | R approx | Assumptions |
|---:|---:|---:|---|
| 0.02 | 0.04 | ≈31 | normal d[r]; σ known-ish |
| 0.05 | 0.06 | ≈11 | same |
| 0.05 | 0.04 | ≈5 | same — but exact Wilcoxon still needs R≥6 to reject |
| 0.08 | 0.05 | ≈4 | normal approx optimistic vs exact |
| 0.10 | 0.06 | ≈3 | normal approx only |

**No pilot estimate of σ_d exists.** Until Plan P (or mock search variance) is run, these rows are **assumption-based ranges**, not measured power.

### 7.2 Exact-test constraint is binding

Even when the normal formula says R≈5, the **exact** two-sided Wilcoxon cannot reject until R≥6. Prefer R=10+ for Plan C.

---

## 8. Planner recommendation (Executor cannot decide)

| Option | Requests (+margin) | Evidence supported |
|---|---:|---|
| Plan P R=1 | 528 | exploratory single-seed candidate contrast only |
| Plan C R=6 | 1,848 | first exact-two-sided-capable design; cost cap may fail |
| Plan C R=10 | 2,904 | better CIs; still conditional on the 40 tasks |
| No D/E yet | 0 | keeps evidence clean |

**Suggestion:** use Plan P only as plumbing/variance scouting under a **new** request+token authorization; promote to Plan C with **R≥6** (prefer 10) when caps are extended. Do **not** run D/E under the 300-request cap. Do **not** call R=1 or R=5 a successful algorithm-level test.

---

## 9. Formula card

```
A=40, B=120, C=80
D_block=120, E_block=120
TOTAL_REQUESTS(R) = 240 + 240 * R
WITH_MARGIN(R)    = ceil(1.1 * TOTAL_REQUESTS(R))

Exact two-sided Wilcoxon rejects at α=0.05 only if R ≥ 6.
Plan P (R=1) = SINGLE_SEED_CANDIDATE_COMPARISON_ONLY.
New real API requests this round: 0.
```
