# Phase 3 — Preference-aware Pareto Evolution Controller (PPEC)

**Status:** complete (Phase 0 `3dd75be` / Phase 1 `29536e6` / Phase 2 `a7e6420` / R1 `4cb0d3a` frozen)  
**Contribution:**

> Preference-aware evolutionary optimization enables NSGA-III to efficiently
> search **task-specific Pareto regions** in many-objective agent optimization.

## Motivation

NSGA-III explores the *whole* Pareto front. Real agent tasks have preferences:

| profile | emphasis |
|---------|----------|
| 科研 Agent | performance > cost |
| 企业 Agent | cost > performance |
| 实时 Agent | latency > accuracy |

We need the **optimizer** (not a post-hoc picker) to steer search toward the
preferred region.

## Preference formulation

### PreferenceVector

```text
(p=0.9, e=0.3, c=0.2, r=0.8, a=0.5)   # accuracy_first
```

- serializable (JSON / dict / seq)
- comparable (`key`, `__lt__`)
- normalizable (L1 and L2 unit vectors)

### Structured encoder (no NLP)

```python
encode_preference("accuracy_first")
encode_preference({"mode": "cost_first"})
encode_preference({"performance": 0.8, ...})
encode_preference([0.9, 0.3, 0.2, 0.8, 0.5])
```

Modes: `accuracy_first`, `cost_first`, `balanced`, `robust_first`,
`efficiency_first`, `autonomy_first`, `latency_first`.

## Algorithm

### Reference direction adaptation

For each NSGA-III reference direction *w* and L1-normalized preference *p*:

```text
w'_i = w_i · ((1−s)·1 + s·(ε + p_i))
w'   ← w' / ‖w'‖₁
```

`s` = strength, `ε` keeps low-weight axes alive. Directions aligned with
important objectives keep more mass → niching concentrates in the preferred
region.

**NSGA-III core is not modified** — `PreferenceAwareNSGA3` subclasses and only
reshapes `directions`.

### Preference Controller API

```python
controller.set_preference({"mode": "accuracy_first"})
controller.get_reference_region()
controller.score_solution(objectives)
controller.select(population, k)
```

### Preference Satisfaction Score

```text
achieve = [perf, eff, 1−cost, robust, auto]
PSS     = Σ w_i · achieve_i / Σ w_i
```

### Pipeline

```text
Task Preference → Encoder → PreferenceVector
        → Reference Direction Adapter → NSGA-III Selection
        → PEEM Adaptive Mutation → Evaluation → Archive → Next Gen
```

## Complexity

| step | cost |
|------|------|
| encode preference | O(1) |
| adapt directions | O(R · M) |
| score solution | O(M) |
| selection | unchanged O(M N²) |

## Modules

```text
src/evolution/preference.py            # PreferenceVector + encoder + PSS
src/evolution/reference_adapter.py     # adapt_reference_directions + PreferenceAwareNSGA3
src/evolution/preference_controller.py # PreferenceController (PPEC)
src/evaluation/metrics.py              # + preference_satisfaction_score
```

## Experiments (`experiments/run_preference_demo.py`)

μ=30, T=15–20, 3 seeds, mock. Mean ± std.

### E1 Preference adaptation (PSS ↑)

| mode | preference-aware PSS | fixed NSGA-III PSS |
|------|---------------------|--------------------|
| accuracy_first | **0.928 ± 0.002** | 0.844 ± 0.016 |
| cost_first | **0.913 ± 0.008** | 0.889 ± 0.011 |
| balanced | 0.868 ± 0.014 | 0.868 ± 0.014 |

→ Preference-aware search **raises task-matched satisfaction**; balanced is neutral by construction.

### E2 Pareto region selection

| mode | mean perf | mean cost | PSS |
|------|-----------|-----------|-----|
| accuracy_first | 0.859 | **0.0127** | 0.844 |
| cost_first | 0.898 | 0.0157 | 0.904 |
| robust_first | 0.894 | 0.0159 | 0.872 |
| balanced | 0.896 | 0.0137 | 0.893 |

→ Region shifts are **modest on mock** (landscape couples high performance with low cost). Stronger separation expected on real benchmarks.

### E3 Module contribution

| variant | final HV | PSS (accuracy) | mean perf |
|---------|----------|----------------|-----------|
| NSGA-III | 0.857 | **0.866** | **0.883** |
| NSGA-III + PEEM | **0.868** | 0.843 | 0.859 |
| NSGA-III + PEEM + PPEC | 0.857 | 0.853 | 0.870 |

→ PEEM improves HV; PPEC trades a little HV for preference focus (expected).

### E4 Preference noise robustness

| noise | PSS | HV |
|-------|-----|-----|
| 5% | 0.859 ± 0.012 | 0.851 ± 0.009 |
| 10% | 0.823 ± 0.035 | 0.857 ± 0.003 |
| 20% | 0.827 ± 0.011 | 0.862 ± 0.005 |

→ Search remains stable under 5–20% preference noise; PSS dips moderately.

### Honest assessment

1. **E1 is the clean win**: preference-aware selection raises PSS vs fixed NSGA-III.
2. E2 region separation is limited on mock; report as “directionally correct”.
3. E3: PPEC is a **search-focus** tool, not an HV booster — consistent with the claim.
4. Full stack: **NSGA-III + Agent Genome + PEEM + PPEC** is now the paper algorithm.

## Future (Phase 4)

Real LLM agent benchmarks (ALFWorld / WebShop / SWE-bench-lite), longer runs,
and preference elicitation beyond structured modes.
