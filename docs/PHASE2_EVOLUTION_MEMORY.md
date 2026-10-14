# Phase 2 — Evolution Experience Memory

**Status:** complete (built on frozen Phase 0 `3dd75be` / Phase 1 `29536e6`)  
**Scope:** **Optimizer memory only** — not agent memory, not RAG, not vector DB.

## Motivation

Classic evolutionary search treats mutations as i.i.d.:

```text
Generation t → random mutation → selection → Generation t+1
```

The optimizer never answers:

- which mutation types historically improved Pareto quality
- which mutations usually fail
- how to allocate mutation effort in the next generation

Phase 2 adds **Evolution Experience Memory** so the search learns *how to mutate*.

## Method

```text
Past evolution trajectories (EvolutionArchive)
        ↓
Mutation effectiveness estimation (MutationExperience)
        ↓
Adaptive mutation distribution (AdaptiveMutationController)
        ↓
Better future search
```

### Core claim (paper)

EvoPareto-Agent is a **many-objective evolutionary agent optimizer that learns
its own search strategy from evolution history** — not merely an LLM prompt
tuner.

## Architecture

```text
Initialize Population
        ↓
Evaluate Agents
        ↓
NSGA-III Selection                (Phase 0, unchanged)
        ↓
Adaptive Mutation Controller      (Phase 2)
        ↓
Generate Children
        ↓
Evaluate Children
        ↓
Update Evolution Archive          (Phase 2)
        ↓
Update Mutation Experience        (Phase 2)
        ↓
(next generation)
```

| Module | File | Role |
|--------|------|------|
| EvolutionRecord / EvolutionArchive | `src/evolution/archive.py` | serializable transition log + HV cache |
| MutationExperience | `src/evolution/experience.py` | per-type success rate / improvement stats |
| AdaptiveMutationController | `src/evolution/adaptive_mutation.py` | experience → mutation probability |
| MutationOperatorRegistry | `src/evolution/adaptive_mutation.py` | extensible operator set |
| MemoryEvolutionLoop | `src/evolution/memory_evolution.py` | full Phase 2 loop |
| hypervolume | `src/evaluation/metrics.py` | HV metric (paper mixed-direction) |

## Algorithm

### 1. Archive record

For each parent→child transition:

```text
objective_delta = child_objectives - parent_objectives
hv_delta        = HV(front ∪ {child}) - HV(front)
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

p(m) = (1-ε) * normalize(scores) + ε * Uniform
p(m) ← max(p(m), min_prob) then renormalize
```

Default ε=0.08 preserves exploration; operator registry is extensible.

### 4. Operators (Phase 0 preserved)

`planner` · `memory` · `reflection` · `tool` · `budget` registered in
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

1. **Credit assignment** — multi-step mutations currently share one
   `mutation_type` label (`planner+budget`). Per-step credit is Phase 3 work.
2. **Contextual bandits** — condition probability on genome features.
3. **Preference-aware control** — user preference over objective tradeoffs
   steering the mutation prior (Phase 3).
4. **Real LLM evaluators** — same archive/experience API.

## Constraints honored

- Phase 0 NSGA-III **unchanged**
- Phase 1 runtime API **compatible**
- No commercial LLM API
- No large external framework
- No agent long-term memory / RAG / vector DB
