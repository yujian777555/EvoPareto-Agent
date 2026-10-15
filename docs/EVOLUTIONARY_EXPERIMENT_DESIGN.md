# Evolutionary Experiment Design (Preregistration)

**Status:** design only — executed only after feasibility gates + Planner approval.  
**Frozen objective (unchanged):**

```python
objective_version = "candidate_2obj"
objective_names = ("performance", "cost")
maximize = (True, False)   # native won rate ↑, estimated cost ↓
```

**Real API calls this round: 0.**

---

## 1. Core hypothesis

**H_PEEM:** reusing Pareto-relevant operator/utility experience (PEEM) improves
search efficiency (hypervolume per evaluation) of NSGA-III on the agent-genome
space under a fixed evaluation budget.

**H_PPEC:** preference-guided control (PPEC) steers sampling toward the
decision-maker's preferred Pareto region without degrading diversity, measured
by preference-aligned hypervolume / IGD+ against a reference set.

**Falsification:**
- If PEEM does not outperform NSGA-III without PEEM on HV-per-evaluation across
  seeds (CI includes 0 or worse), H_PEEM is not supported.
- If PPEC's preferred region is not reached faster / more reliably than
  unguided NSGA-III+PEEM, H_PPEC is not supported.
- If all methods score `performance=0` on all tasks, **neither hypothesis is
  testable** — the experiment is invalid until solvability is established.

## 2. Arms (minimum)

| Arm | Role |
|---|---|
| 1. Random Search | floor |
| 2. NSGA-II | competitive many-objective baseline (2-D often favors NSGA-II) |
| 3. NSGA-III | target algorithm |
| 4. NSGA-III + PEEM | PEEM ablation |
| 5. NSGA-III + PEEM + PPEC | full method |
| 6. (optional) NSGA-III + PPEC without PEEM | interaction split |

### Does PPEC require PEEM?
Inspect `src/evolution/preference_2d.py` + selection path: if PPEC reads PEEM
utility estimates, Arm 6 must either (a) run PPEC with uniform/neutral
utilities as a documented ablation, or (b) state that PPEC-without-PEEM is
ill-defined and use a 2×2 factorial (PEEM on/off × PPEC on/off) with a
neutral-utility PPEC cell.

**No arm may receive extra real-evaluation budget, extra tasks, or a stronger
agent phenotype than another.**

## 3. Fairness requirements (frozen)

- Same genome encoding and legal mutation operators for all arms.
- Same frozen task pool and **held-out** evaluation protocol; development tasks
  never used for final tables.
- Same DeepSeek backend, model id, rate table, and cost formula.
- Same per-candidate evaluation cost accounting (physical tickets + usage).
- Same total physical HTTP / dollar evaluation budget **per arm**.
- Independent seeds; ≥ 5 seeds per arm for formal claims (or state power limit).
- Failures / timeouts / BillingBlocked count as failures with their real cost.
- No test-set tuning of preferences or reference points.

## 4. Metrics

| Metric | Definition (frozen) |
|---|---|
| Native task success rate | mean of `won` over frozen eval tasks |
| Estimated inference cost | peak-conservative rate × real tokens |
| Hypervolume | 2-D HV with **fixed** reference point (below) |
| HV per evaluation | HV curve vs number of evaluations (AUC optional) |
| IGD+ | only if a justified reference set is defined **before** runs |
| Pareto set quality | non-dominated count + spread |
| Stability | per-seed mean ± std of HV and success rate |

### Hypervolume normalization (frozen)

```
objectives: performance ∈ [0,1] (won rate), cost ∈ [0, C_max]
normalization: p' = p, c' = c / C_max
reference point: (p_ref, c_ref) = (0.0, 1.0)   # maximize p, minimize c' → ref below/right
HV computed on non-dominated set of (p', -c') in maximization form
C_max = the frozen cost cap of the experiment (declared before runs)
```

Reference point and C_max must not be changed after seeing results.

## 5. NSGA-III vs NSGA-II in 2-D — honest framing

For **two** objectives, NSGA-III's niching advantage is not automatic; NSGA-II
is a fully legitimate competitor. The paper must either:
- show empirically that reference-direction niching helps the **discrete,
  multi-modal genome landscape** (not just cite many-objective lore), or
- position NSGA-III as the chosen vehicle and still report NSGA-II fairly.

Random search is a floor, not a strawman: with tiny budgets it can be strong.

## 6. Preference resource asymmetry

PPEC uses preference information. Fair comparison options:
1. Fix one global preference for the whole run (declared up front), or
2. Evaluate several methods with the same preference oracle, or
3. Report preference-agnostic HV **and** preference-aligned metrics.

Do not give PPEC extra evaluations to "find" preferences.

## 7. PEEM/PPEC evidence standards

PEEM/PPEC benefit must appear as:
- faster HV growth per evaluation, and/or
- better final HV / IGD+ at equal budget, and/or
- higher success at matched cost,

with seed-level statistics (paired where tasks are shared). Overlapping CIs or
single-seed wins are **not** sufficient.

## 8. Phase order

1. Feasibility block (LIVE_FEASIBILITY_PREREGISTRATION.md) → Gates 1–3.
2. If Gate 1 fails: fix solvability/phenotype before any arm comparison.
3. If Gates 1–3 pass: run the arms above under the frozen protocol.
4. Only then claim PEEM/PPEC effects — or honestly report their absence.
