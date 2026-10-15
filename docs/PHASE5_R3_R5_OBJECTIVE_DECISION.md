# Phase5-R3-R5 — Objective Decision (for Planner)

## Q2: why 5-obj is not fully valid

| obj | problem | evidence |
|-----|---------|----------|
| efficiency | quick-fail scores higher than success | construction case + counterexamples |
| robustness | ≡ perf×(1−stall); 0 when all fail | redundancy test |
| autonomy | proxy from budget/stall, not behavior | audit |

performance / cost remain sound.

## Plan A — keep 5 objectives (repaired)

```text
efficiency = mean_i [ 1/(1+s_i/H+tok_i/2000)  if success else 0.3 * raw ]
robustness = mean(success) - 0.5 * Var(success)
autonomy   = 1 - fallback_rate - 0.5*external_help_rate
```

Pros: multi-axis PPEC story.  
Cons: still needs multi-instance protocol; more failure modes.

## Plan B — two objectives

```text
max performance = success rate
min cost        = mean API $
diagnostics     = steps, tokens (not optimized)
```

Pros: construct validity; matches native evidence.  
Cons: 2D NSGA-III ≈ NSGA-II; weaker “many-objective” novelty.

## 2D NSGA-III check

`generate_reference_directions(2, H=4)` → 5 directions on the simplex — valid.
PEEM credit works on any fitness width; PPEC reference adaptation still shifts
2D weights. **Need NSGA-II baseline if adopting Plan B.**

## Recommendation

**Adopt Plan B (performance + cost) as formal objectives for the next pilot**;
keep Plan A as secondary protocol after multi-instance robustness is ready.

Do not mix versions in one table (`legacy_5obj` / `candidate_5obj` / `candidate_2obj`).

Awaiting Planner freeze.
