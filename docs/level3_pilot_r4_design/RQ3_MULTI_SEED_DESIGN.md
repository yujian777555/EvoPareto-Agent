# RQ3 Multi-Seed Design — Plan P vs Plan C (R4-R2)

**Status:** DESIGN ONLY — zero real model calls. Not an authorization.
**Baseline commit:** `d1056059e73b46225dd4218b98a9948af7627b19`.
**Question this document prices:** can we claim that *two-generation evolution* stably beats *random search*, not merely that one lucky search seed produced a better candidate?

---

## 1. Why a single search seed is insufficient

With one seed per method (old 480-call plan):

* The unit of comparison is **one selected candidate workflow vs another**, both scored on the same 40 confirmation tasks.
* A confirmation-set difference (even a significant McNemar result) speaks to **those two candidates**, not to the **search algorithms**.
* Search RNG variance is completely confounded with method effect.

Therefore RQ3 at the **algorithm** level requires independent search replications.

---

## 2. Plan P — single-search exploratory pilot

| Item | Value |
|---|---|
| A / B / C | one run each |
| D / E | **one** search seed each |
| Confirmation | same 40 tasks for all groups |
| Request formula | `240 + 240×1 = 480` |
| Inference allowed | *“Under this seed, E's selected candidate beat / lost to D's selected candidate on these 40 tasks.”* |
| Inference **not** allowed | “Evolutionary search is better than random search” / any algorithm-level claim |
| Role | plumbing + variance scouting; optional precursor to Plan C |

**Evidence boundary (must be printed next to any Plan P result):**  
`SINGLE_SEED_CANDIDATE_COMPARISON_ONLY — not an algorithm-level test.`

---

## 3. Plan C — algorithm-level multi-seed comparison

### 3.1 Structure

* A, B, C: still **one** reference run each (they are not search procedures).
* D and E: **R independent search seeds** each (`R ∈ {1, 5, 10}` reported).
* Per seed: same `m=4` candidates, same development set size `s=20`, same confirmation set (40 tasks).
* Final workflow per seed is scored once on the confirmation set.
* **D and E request budgets match inside each seed** (120 vs 120).

### 3.2 Request accounting

| Component | Formula | R=1 | R=5 | R=10 |
|---|---|---:|---:|---:|
| A | 40 | 40 | 40 | 40 |
| B | 120 | 120 | 120 | 120 |
| C | 80 | 80 | 80 | 80 |
| D × R | 120 R | 120 | 600 | 1200 |
| E × R | 120 R | 120 | 600 | 1200 |
| **TOTAL** | **`240 + 240 R`** | **480** | **1,440** | **2,640** |
| vs current 300-request cap | | **+180** | **+1,140** | **+2,340** |
| 10% retry/safety margin | 0.1×TOTAL | 48 | 144 | 264 |
| **With margin** | | **528** | **1,584** | **2,904** |

**No silent reduction:** if authorization cannot cover R, the study is reported `INCOMPLETE`; seeds / confirmation tasks / contrasts are not quietly dropped.

### 3.3 Token and cost estimates (estimate ≠ invoice)

Per-request bounds (from R3 observed mix): input 150–400, output 150–800 (median ~300).

| R | TOTAL req | input tok (low–high) | output tok (med) | output tok (high) | worst-case USD (=$0.003/req) | settled-rate USD (≈$0.00016) |
|---:|---:|---|---|---|---:|---:|
| 1 | 480 | 72k–192k | ≈144k | 384k | **$1.44** | ≈$0.08 |
| 5 | 1,440 | 216k–576k | ≈432k | 1.15M | **$4.32** | ≈$0.23 |
| 10 | 2,640 | 396k–1.06M | ≈792k | 2.11M | **$7.92** | ≈$0.42 |

**Cap checks (existing authorization):**

| Cap | R=1 | R=5 | R=10 |
|---|---|---|---|
| requests ≤ 300 | **FAIL** (480>300) | **FAIL** | **FAIL** |
| output tokens ≤ 200,000 | **FAIL** at high bound (384k); risky at median (144k) | **FAIL** | **FAIL** |
| cost ≤ $5.00 | PASS worst-case $1.44 | PASS $4.32 | **FAIL $7.92** |

**New authorization required** even for Plan P / R=1. This is the main gate.

---

## 4. Statistical design (Plan C)

### 4.1 Analysis units — must be distinguished

| Unit | What varies | Role |
|---|---|---|
| **Task** (n=40) | question difficulty | paired correctness within a seed |
| **Search seed** (n=R) | candidate-generation RNG | **primary unit for algorithm claims** |
| **Task × seed** (n=40R) | both | descriptive only; **not** 40R independent Bernoulli trials |

Same confirmation task scored by multiple seeds is **not** independent evidence. Treating 40R rows as i.i.d. would inflate significance.

### 4.2 Recommended primary contrast (algorithm level)

For each seed `r=1..R` compute confirmation accuracy `acc_D[r]` and `acc_E[r]` (proportion of 40).

* Difference series `d[r] = acc_E[r] − acc_D[r]`.
* **Primary test:** exact Wilcoxon signed-rank on `d[r]` (or one-sample t if R is large and d looks normal) — two-sided, α=0.05.
* Report mean/median `d`, bootstrap CI over seeds, and min/max.
* **Secondary (candidate level, per seed):** McNemar on that seed's two selected candidates; apply Holm across seeds if interpreted as a family.

### 4.3 Missing / failure rules

* A seed that cannot produce a valid candidate → dev accuracy 0, candidate retained; if the seed cannot score confirmation, that seed is `FAILED_SEED` and **remains in the R denominator** as a pre-declared worst case (or is listed as missing with the primary analysis using available seeds + sensitivity with failed seeds scored 0). Pre-declare: **failed seed scores 0 accuracy for that method**.

### 4.4 Power / sample size stance (offline)

Let `μ_d` be the true mean seed-level accuracy difference and `σ_d` the seed-level SD of differences.

Rough normal-approx for two-sided paired t / Wilcoxon-approx:

`R ≈ ((z_{1-α/2} + z_{1-β}) * σ_d / μ_d)^2`

| Assumed `μ_d` | Assumed `σ_d` | R for 80% power (α=0.05) |
|---:|---:|---:|
| 0.02 (2 points) | 0.04 | ≈ 62 |
| 0.05 (5 points) | 0.06 | ≈ 23 |
| 0.05 | 0.04 | ≈ 10 |
| 0.08 | 0.05 | ≈ 5 |
| 0.10 | 0.06 | ≈ 4 |

**Reading.** R=5 or R=10 is only powered for **large, stable** seed-level effects. R=1 cannot test algorithms at all. Report the detectable `μ_d` at each R rather than pretending R=10 is “enough for anything”.

There is **no pilot estimate of σ_d** yet (we have never run D/E). Until Plan P or a mock search gives a variance estimate, these ranges are assumption-based.

---

## 5. Statistical dependence handling (explicit)

1. Confirmation set is **fixed and shared** across all seeds and both methods (paired by design).
2. Algorithm inference is over **seeds**, not tasks.
3. Task-level McNemar within a seed describes *that seed's candidates*; it is secondary.
4. Do not pool 40R task rows into one McNemar.
5. If reporting task-level effects across seeds, use a hierarchical model or cluster-robust SE at the seed level — and label it exploratory.

---

## 6. Planner recommendation (Executor cannot decide)

| Option | Cost | What it can support | Risk |
|---|---|---|---|
| **Plan P (R=1)** now, after new auth for ~528 req | lower | exploratory candidate contrast + variance scouting for a later Plan C | over-claiming risk if not labelled |
| **Plan C with R=5** (1,584 req with margin) | medium-high | algorithm-level test for moderate–large effects | still underpowered for tiny effects; token cap must rise |
| **Plan C with R=10** (2,904 req with margin) | high | better seed-level CIs; detectable μ_d ≈ 0.05 if σ_d≈0.04 | cost cap $5 also breached (≈$7.92 worst-case) |
| Do not run D/E yet | 0 | keeps evidence clean | RQ3 unanswered |

**Executor suggestion for Planner:** treat Plan P as a *variance-scoping pilot* under a new request/token authorization, and only promote to Plan C when (a) σ_d can be estimated and (b) request + token + cost caps are explicitly extended. **Do not** run D/E under the current 300-request cap and **do not** call R=1 an algorithm test.

---

## 7. Fixed formula summary

```
A = 40, B = 120, C = 80
D_seed = 120, E_seed = 120
TOTAL_REQUESTS(R) = 240 + 240 * R

R=1   -> 480    (Plan P baseline)
R=5   -> 1440
R=10  -> 2640

+10% safety -> 528 / 1584 / 2904
```

New real API requests this round: **0**.

