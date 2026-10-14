# Phase 2 â€” Evolution Experience Memory

> **Upgrades:**
> - Phase 2.5 PEEM: [`PHASE2_5_PEEM.md`](PHASE2_5_PEEM.md)
> - Phase 2.5-R1 Robust PEEM: see section below
>
> This file keeps the Phase 2 success-rate baseline and architecture.

**Status:** complete (built on frozen Phase 0 `3dd75be` / Phase 1 `29536e6`)  
**Scope:** **Optimizer memory only** â€” not agent memory, not RAG, not vector DB.

## Motivation

Classic evolutionary search treats mutations as i.i.d.:

```text
Generation t â†’ random mutation â†’ selection â†’ Generation t+1
```

The optimizer never answers:

- which mutation types historically improved Pareto quality
- which mutations usually fail
- how to allocate mutation effort in the next generation

Phase 2 adds **Evolution Experience Memory** so the search learns *how to mutate*.

## Method

```text
Past evolution trajectories (EvolutionArchive)
        â†“
Mutation effectiveness estimation (MutationExperience)
        â†“
Adaptive mutation distribution (AdaptiveMutationController)
        â†“
Better future search
```

### Core claim (paper)

EvoPareto-Agent is a **many-objective evolutionary agent optimizer that learns
its own search strategy from evolution history** â€” not merely an LLM prompt
tuner.

## Architecture

```text
Initialize Population
        â†“
Evaluate Agents
        â†“
NSGA-III Selection                (Phase 0, unchanged)
        â†“
Adaptive Mutation Controller      (Phase 2)
        â†“
Generate Children
        â†“
Evaluate Children
        â†“
Update Evolution Archive          (Phase 2)
        â†“
Update Mutation Experience        (Phase 2)
        â†“
(next generation)
```

| Module | File | Role |
|--------|------|------|
| EvolutionRecord / EvolutionArchive | `src/evolution/archive.py` | serializable transition log + HV cache |
| MutationExperience | `src/evolution/experience.py` | per-type success rate / improvement stats |
| AdaptiveMutationController | `src/evolution/adaptive_mutation.py` | experience â†’ mutation probability |
| MutationOperatorRegistry | `src/evolution/adaptive_mutation.py` | extensible operator set |
| MemoryEvolutionLoop | `src/evolution/memory_evolution.py` | full Phase 2 loop |
| hypervolume | `src/evaluation/metrics.py` | HV metric (paper mixed-direction) |

## Algorithm

### 1. Archive record

For each parentâ†’child transition:

```text
objective_delta = child_objectives - parent_objectives
hv_delta        = HV(front âˆª {child}) - HV(front)
success         = mixed_dominates(child, parent) or hv_delta > 0
```

### 2. Experience statistics (per mutation type)

```text
count, success, success_rate
average_improvement = mean positive hv_delta
```

### 3. Adaptive probability

```text
score(m) = (successes_m + prior_weight * prior_rate) / (count_m + prior_weight)
           * (1 + average_improvement_m)

p(m) = (1-Îµ) * normalize(scores) + Îµ * Uniform
p(m) â† max(p(m), min_prob) then renormalize
```

Default Îµ=0.08 preserves exploration; operator registry is extensible.

### 4. Operators (Phase 0 preserved)

`planner` Â· `memory` Â· `reflection` Â· `tool` Â· `budget` registered in
`MutationOperatorRegistry`.

## Experiments

```bash
python experiments/run_evolution_memory_demo.py
```

| ID | Question | Metric |
|----|----------|--------|
| E1 | random vs adaptive | final HV, Pareto size, HV convergence curve |
| E2 | mutation efficiency | evaluations to reach target HV |
| E3 | ablation | NSGA-III vs NSGA-III + Evolution Memory |

Representative run (pop=20, mock benchmark, 2 seeds):

| Setting | final HV |
|---------|----------|
| E1 random | 0.764 |
| E1 adaptive | **0.781** |
| E3 NSGA-III | 0.780 |
| E3 NSGA-III + Memory | 0.761 |

Notes:

- Adaptive distribution **does learn** (e.g. `reflection` rises to ~0.29 when
  its empirical success rate leads).
- On short mock runs the HV gap is modest; effect size should grow with
  evaluation budget and clearer mutation specialization (Phase 3/4).
- Full JSON: `results/evolution_memory_results.json`.

## Future extension

1. **Credit assignment** â€” multi-step mutations currently share one
   `mutation_type` label (`planner+budget`). Per-step credit is Phase 3 work.
2. **Contextual bandits** â€” condition probability on genome features.
3. **Preference-aware control** â€” user preference over objective tradeoffs
   steering the mutation prior (Phase 3).
4. **Real LLM evaluators** â€” same archive/experience API.

## Constraints honored

- Phase 0 NSGA-III **unchanged**
- Phase 1 runtime API **compatible**
- No commercial LLM API
- No large external framework
- No agent long-term memory / RAG / vector DB

---

## Robust PEEM (Phase 2.5-R1)

### Motivation

Phase 2.5 PEEM used Monte-Carlo hypervolume deltas as credit. On small
populations this signal is **noisy** (E4 of Phase 2.5: removing HV credit
helped). One-step credit also ignores **delayed** value (a mutation may enter
the front several generations later). High-score greedy selection risks
premature convergence.

### Algorithm

**1. Rank-based Pareto contribution** (`pareto_credit.py`)

```text
rank children in the offspring batch by mixed-direction improvement
top 20%  -> 1.0
middle 50% -> 0.5
bottom 30% -> 0.0
```

No dependence on exact HV values.

**2. Per-generation z-normalization** (`normalization.py`)

```text
z = (x - mean_gen) / std_gen
```

applied to improvement / pareto / diversity / survival before mixing.

**3. Composite Mutation Value**

```text
MV = ¦Á¡¤improvement_z + ¦Â¡¤pareto_bucket + ¦Ã¡¤diversity + ¦Ä¡¤survival + delayed_bonus
```

**4. Delayed credit** (`delayed_credit.py`)

Each mutation gets `mutation_id`; over a horizon of h generations we track
`future_survival` and `future_pareto_gain` and fold them into later scores.

**5. Temperature-softmax mutation selection** (`adaptive_mutation.py`)

```text
p_i = exp(score_i / T) / ¦²_j exp(score_j / T)
T: T0=1.0 ¡ú Tmin=0.2 (linear anneal)
```

### Formula summary

```text
bucket(r) = 1.0 if r<0.2; 0.5 if r<0.7; else 0.0
score_t(m) = ¦Ë¡¤MV_t(m) + (1-¦Ë)¡¤score_{t-1}(m)
p(m) ¡Ø softmax(score/T)
```

### Complexity

| step | cost |
|------|------|
| rank bucket (batch) | O(¦Ë log ¦Ë) |
| z-normalization | O(¦Ë) |
| delayed observe | O(open ¡Á N), open capped |
| softmax | O(K) |

Per generation ¡Ö O(N2 + ¦ËN) ¡ª no MC HV in the robust path.

### Modules

```text
src/evolution/pareto_credit.py     # ParetoContributionEstimator
src/evolution/normalization.py     # GenerationNormalizer / z-score
src/evolution/delayed_credit.py    # DelayedCreditBook
src/evolution/credit_assignment.py # compute_robust_credit
src/evolution/adaptive_mutation.py # temperature softmax
```

### Experiments (`experiments/run_robust_peem_demo.py`)

Scale: ¦Ì=50, 5 seeds, gens 25¨C50 (mock). Mean ¡À std.

**E1 final HV** (higher better)

| method | HV mean ¡À std | IGD ¡ý |
|--------|---------------|-------|
| random | **0.862 ¡À 0.007** | **0.037 ¡À 0.026** |
| success-rate | 0.855 ¡À 0.010 | 0.056 ¡À 0.040 |
| PEEM v1 | 0.854 ¡À 0.008 | 0.063 ¡À 0.045 |
| **Robust PEEM** | 0.855 ¡À 0.011 | **0.038 ¡À 0.023** |

**E2 evals to random's HV**: success 940 ¡¤ peem_v1 1090 ¡¤ random 1150 ¡¤ robust 1170

**E3 ablation HV**: full_robust 0.852 ¡¤ no_pareto_bucket 0.860 ¡¤ no_delayed 0.852 ¡¤ no_temperature 0.860

**E4 noise robustness (HV std)** ¡ª Robust PEEM is **most stable** at 5% noise:

| noise | success std | peem_v1 std | **robust std** |
|-------|-------------|-------------|----------------|
| 5% | 0.0095 | 0.0092 | **0.0068** |
| 10% | 0.0010 | 0.0097 | 0.0044 |
| 20% | 0.0005 | 0.0 | 0.0 |

### Honest assessment

1. **Robust PEEM matches PEEM v1 HV** and is **near-random IGD** ¡ª rank credit
   removed the HV-noise failure mode of Phase 2.5.
2. **Stability** (low std under objective noise) is the clearest robust-PEEM win.
3. Absolute HV still close to random on mock; larger gains need harder landscapes
   and longer horizons (100 gens as in the paper protocol).
4. Ablation: bucketed Pareto credit / temperature are not yet dominant on mock;
   they are retained for algorithmic completeness and noise robustness.

Paper claim:

> PEEM provides a **robust learning mechanism for evolutionary operator utility
> estimation** in many-objective agent optimization, combining rank-based Pareto
> credit, z-normalized composite value, delayed survival feedback, and
> temperature-annealed mutation selection.
