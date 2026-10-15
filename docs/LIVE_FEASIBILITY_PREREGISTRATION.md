# Live Feasibility Preregistration

**Status:** DESIGN ONLY — **not executed**. Requires Planner budget approval.  
**Prior live evidence:** 1 episode (Pilot 1), `won=false`, $0.0026718, 30 HTTP.  
**Real API calls this round: 0.**

---

## 1. Core scientific question

> Under the same evaluation budget, can PEEM/PPEC help NSGA-III search a
> meaningful Performance–Cost Pareto set more effectively than baselines?

A prerequisite: the frozen agent/genome space must produce **non-zero and
variable** native `won` signals. Otherwise multi-objective search degenerates.

## 2. Pilot-1-derived risk

- Single genome, single task: `won=false` after 29 steps of looping.
- Genome phenotype space is partially degenerate (see GENOME_PHENOTYPE_AUDIT).
- If every genome fails every task, objective 2 (cost) becomes the only
  gradient → "cheaper failure" looks optimal. **This is the dominant risk.**

## 3. Proposed feasibility design (candidate — not a permission to run)

```
6 × ALFWorld valid_train tasks   ×  3 preregistered Genomes  ×  2 seeds
= 36 episodes
```

### 3.1 Frozen task set (proposed)

Take indices `{0, 5, 10, 15, 20, 25}` from
`results/native_alfworld/development_task_pool.json` (50 tasks).
**Freeze this list and its manifest SHA256 before any run.** Same tasks for
every genome and seed.

### 3.2 Preregistered genomes (mechanism-distinct, fixed now)

| ID | planner | memory | reflection | tool_policy | budget | Why |
|---|---|---|---|---|---|---|
| G1 | cot | short_term | self_critique | balanced | 64 | Pilot 1 baseline |
| G2 | plan_and_solve | episodic | none | conservative | 64 | memory history + no reflection + prompt plan |
| G3 | direct | none | none | no_tools | 16 | minimal memory/reflection, short budget (cost floor) |

Rationale: span the **behaviorally real** genes (memory none/short/episodic,
reflection none vs retry, budget 16 vs 64). `tool_policy` is currently a no-op
on native path — kept only to match legal genome schema.

**No genome may be swapped after results are seen.**

### 3.3 Shared frozen protocol

| Item | Value |
|---|---|
| model | `deepseek-flash` |
| rate_version | `deepseek-flash-2026-10-peak-conservative-v1` |
| environment | native ALFWorld TextWorld |
| split | `valid_train` |
| horizon | 30 |
| objective | `candidate_2obj` = (won performance ↑, estimated cost ↓) |
| execution layer | identical InteractiveAgent + EpisodeRunner |
| retries | none (fail-closed) |
| stop | BillingBlocked / identity mismatch / budget |
| seeds | `{11, 23}` for every genome×task |
| success | native `won` only |

### 3.4 Budget estimate (see feasibility_budget_estimate.json)

Pilot 1 episode: 30 HTTP · 8418 in · 122 out · **$0.0026718**.

| Scenario | HTTP / ep | Cost / ep | 36-ep HTTP | 36-ep cost |
|---|---:|---:|---:|---:|
| Low (3 calls, early stop) | 3 | ≈$0.0004 | 108 | ≈$0.014 |
| **Median (Pilot 1)** | 30 | $0.00267 | 1080 | **$0.096** |
| High (35 calls + margin) | 35 | ≈$0.0047 | 1260 | ≈$0.168 |

**Recommended request to Planner:**  
physical HTTP cap **1400**, estimated-cost cap **$0.25** (local estimate, not
invoice). Reservation = 2000 in + 128 out × peak rates per attempt; actual
settles to true usage. Assume off-peak discounts are **not** applied.

If Planner deems $0.25 too large: shrink to 3 tasks × 3 genomes × 2 seeds = 18
episodes (≈$0.05–$0.08) — weaker Gate 2 power but still answers Gate 1.

## 4. Decision gates (frozen before results)

### Gate 1 — Real task solvability
**Pass:** at least 1 episode with native `won=true` across the 36 (or 18).  
**Fail:** 0 successes → **stop expanding evolutionary search**. Next step is
benchmark/policy suitability (different tasks, easier split, or agent repair),
**not** a bigger population.

### Gate 2 — Genome distinguishability
On the **same task×seed pairs**, genomes must show reproducible differences in
either won-rate or step/token/cost profile **beyond one lucky episode**.  
**Pass rule (frozen):** at least one genome-pair with differing outcomes on
≥ 2 matched (task, seed) pairs, or non-overlapping cost distributions with
Kolmogorov–Smirnov p < 0.1 on the paired sample.  
**Fail:** no signal → phenotype space too degenerate; fix phenotypes before
any PEEM/PPEC claim.

### Gate 3 — Multi-objective signal
**Pass:** the set of evaluated points has ≥ 2 non-dominated (performance, cost)
outcomes with performance > 0 for at least one point, **or** (if all won=0) a
documented decision that the design must change.  
**No re-labeling progress proxies as performance.**

Thresholds here are frozen; they may **not** be relaxed after seeing data.

## 5. What this experiment does NOT do

- Not a PEEM/PPEC superiority claim.
- Not a substitute for the five-arm evolutionary comparison.
- Not allowed to cherry-pick tasks after results.
- Not allowed to spend real API without a new Planner approval.

## 6. Request to Planner

Approve (or shrink) the feasibility block:
**36 episodes · cap 1400 HTTP · cap $0.25 estimated**  
or the reduced 18-episode variant. Awaiting explicit budget authorization.
