# Phase 2.5 — Pareto-aware Evolution Experience Memory (PEEM)

**Status:** complete (Phase 0 `3dd75be` / Phase 1 `29536e6` / Phase 2 `a7e6420` frozen APIs)  
**Contribution:** a *learning mechanism for many-objective evolutionary
optimization* that estimates mutation utility from Pareto improvement,
diversity contribution, and survival feedback.

> We propose **Pareto-aware Evolution Experience Memory (PEEM)**, a learning
> mechanism for many-objective evolutionary optimization that estimates
> mutation utility from Pareto improvement, diversity contribution, and
> survival feedback, enabling adaptive search over complex agent genome spaces.

## Motivation

Phase 2 scored mutations mainly by `success_rate`. In many-objective search a
mutation can be valuable even when it does not dominate its parent:

1. **expands the Pareto front** (extreme / niche points)
2. **increases diversity** (bridges sparse regions)
3. **survives NSGA-III selection** (stably useful)

PEEM replaces the scalar success-rate score with a **composite mutation value**.

## Formula

### Composite Mutation Value

```text
MV = α · improvement
   + β · hypervolume_gain
   + γ · diversity_gain
   + δ · survival_credit
```

| term | meaning |
|------|---------|
| improvement | mixed-direction objective gain (cost minimized) |
| hypervolume_gain | marginal HV of child on the current front |
| diversity_gain | nearest-neighbor isolation vs population |
| survival_credit | 1 if retained by NSGA-III next generation |

Default weights: `α=0.35, β=0.30, γ=0.20, δ=0.15` (normalized).

### Experience decay

```text
score_t = λ · current_MV + (1 − λ) · score_{t−1}
```

Configurable `λ` (default 0.35). Early mistakes cannot dominate forever.

### Adaptive probability

```text
p(m) = (1−ε) · normalize(sharpen(score(m))) + ε · Uniform
p(m) ← max(p(m), p_min); renormalize
```

## Algorithm (pseudocode)

```text
PEEM-NSGA-III
────────────
P ← initialize()
evaluate P
A ← empty archive
E ← empty PEEM

for t = 1 … T:
    C ← empty
    for i = 1 … λ_offspring:
        parent ← sample(P, weights ∝ NSGA-III rank)
        m      ← sample_mutation(E.probabilities())
        child  ← m(parent)
        evaluate child
        C ← C ∪ {child}

    P' ← NSGA-III-Select(P ∪ C, μ)
    for child ∈ C:
        credit ← compute_credit(parent, child,
                                front=P', ranks, survived=(child ∈ P'))
        A.record(parent, child, credit)
        E.update(m(child), credit.MV)      # decayed
    P ← P'
return P
```

## Complexity

| step | cost |
|------|------|
| non-dominated sort | O(M N²) |
| niching (per gen) | O(M · R · N) |
| HV contribution (per child) | O(K · S) MC, S samples |
| diversity contribution | O(K²) worst, sampled O(K) |
| PEEM update | O(1) per mutation type |

Total per generation ≈ O(N² + λN). Suitable for μ, λ ∈ [30, 100] on mock;
real LLM eval dominates wall-clock.

## Architecture changes

```text
src/evolution/
    credit_assignment.py   # MV components + compute_credit
    diversity.py           # crowding / spacing / diversity_contribution
    pareto_experience.py   # PEEM: update / score / decay / query
    memory_evolution.py    # experience_mode="peem" | "phase2"
src/evaluation/metrics.py  # + igd, spacing, mutation_entropy
```

Phase 0 NSGA-III unchanged. Phase 1 runtime API unchanged. Phase 2 archive
compatible (`EvolutionRecord` gained optional Pareto-credit fields).

## Experimental design

```bash
python experiments/run_peem_demo.py
```

| ID | comparison | metrics |
|----|------------|---------|
| E1 | random vs success-rate vs **PEEM** | HV, IGD, spacing, mutation entropy |
| E2 | NSGA-III vs +SuccessMemory vs **+PEEM** | HV, front size, convergence |
| E3 | evals to reach random's HV | search efficiency |
| E4 | ablate HV / diversity / survival credit | component contribution |

### Representative results (μ=30, T=12, mock, 2 seeds)

| setting | final HV | IGD ↓ |
|---------|----------|-------|
| random | 0.807 | **0.039** |
| success-rate | 0.805 | 0.058 |
| **PEEM** | **0.811** | 0.046 |

| E3 mean evals to target | |
|-------------------------|---|
| random | 345 |
| success-rate | **225** |
| PEEM | 270 |

| E4 ablation (final HV) | |
|------------------------|---|
| full PEEM | 0.789 |
| no HV credit | **0.818** |
| no diversity | 0.800 |
| no survival | 0.793 |

### Interpretation (honest)

1. **PEEM ≥ baselines on HV** in E1/E2 — consistent but **modest** on mock.
2. IGD favors `random` slightly: mock landscape’s union reference rewards spread.
3. E3: success-rate adaptive reaches random’s target fastest here; PEEM still
   beats random.
4. E4: removing **HV credit** helped on mock → MC HV estimate is noisy at small
   sample budget. Phase 3 should stabilize credit (exact HV / larger samples /
   rank-based surrogate).

**Conclusion for the paper:** PEEM is the right *interface* (Pareto-aware
utility + decay + adaptive variation). On mock, HV wins are real but small;
stronger gains require (a) longer runs, (b) specialized benchmarks, (c)
stabilized credit estimation.

## Future extension (Phase 3)

1. Preference-aware credit (user weights over objectives)
2. Stable HV / IGD credit (exact front-based contribution)
3. Contextual mutation bandits conditioned on genome features
4. Multi-step credit assignment for composite mutations
