> **Audit notice (2026-10-22): historical results below are not paper-ready until rerun.**
> The original `B0_random_search` and `B3_nsga3` entries used the same
> `MemoryEvolutionLoop` configuration, so B0 was not an independent random
> search. The repair and acceptance checklist are documented in
> [PHASE5_BENCHMARK_BASELINE_REPAIR.md](PHASE5_BENCHMARK_BASELINE_REPAIR.md).
> The repaired runner also computes final HV on the cumulative archive of all
> candidate evaluations. Existing numbers below are retained as historical
> records and must not be presented as post-repair results. ReAct is a fixed
> reference configuration, not a 108-evaluation optimizer.
>
> **Current status:** baseline code repaired; tests and benchmark rerun pending.
>
> ---
>
# Phase 5 — Benchmark Extension (WebShop + NSGA-II)

**Status:** complete (algorithms frozen; adapters, baselines, experiments only)

**Paper claim under test:**

> PEEM-PPEC provides a **general** many-objective evolutionary optimization
> framework for adaptive LLM agents **across different task environments**.

---

## 1. Benchmark motivation

| env | focus | why |
|-----|-------|-----|
| **ALFWorld** | planning / long horizon | household sequential tasks |
| **WebShop** | **cost-performance tradeoff** | search→click→buy; natural token/step/cost axes |

Adding WebShop answers the “only planning agents?” reviewer risk.

## 2. Environment description

`src/benchmark/webshop_real.py` implements `BenchmarkAdapter`
(`reset / run / evaluate`) with the **same episode schema** as ALFWorld:

```json
{ "task_id", "genome", "success", "steps", "tokens", "latency", "cost", "trajectory" }
```

5 shopping templates (mug / headphones / basket / shoes / gift), difficulty 0.50–0.78.
LLM backend + evaluation cache shared with ALFWorld.

## 3. Baselines (unified matrix)

| id | method |
|----|--------|
| B0 | Random search |
| B1 | ReAct (fixed genome) |
| **B2** | **NSGA-II** (new baseline) |
| B3 | NSGA-III |
| B4 | NSGA-III + PEEM |
| B5 | NSGA-III + PEEM + PPEC |

### NSGA-II (`src/evolution/nsga2_baseline.py`)

Standard: non-dominated sorting · crowding distance · binary tournament.
**NSGA-III core untouched** — NSGA-II is a drop-in selector baseline.

## 4. Metrics & protocol

Success · Cost · Steps · HV · IGD · PSS  
μ=12, G=8, tasks=10, **3 seeds**, **fixed 108 evaluations/run** for every method.

---

## 5. Cross-benchmark results (mean ± std)

### ALFWorld (planning)

| Method | Success | Cost | HV | IGD ↓ | PSS |
|--------|---------|------|-----|-------|-----|
| B0 Random | 0.822±0.055 | 0.00114 | 0.748±0.033 | 0.055 | 0.826 |
| B1 ReAct | 0.400 | 0.00131 | — | 0.818 | — |
| B2 NSGA-II | 0.811±0.052 | 0.00113 | 0.750±0.032 | 0.055 | 0.818 |
| B3 NSGA-III | 0.822±0.055 | 0.00114 | 0.748±0.033 | 0.055 | 0.826 |
| **B4 +PEEM** | **0.883±0.062** | 0.00116 | **0.771±0.020** | **0.039** | **0.861** |
| B5 +PEEM+PPEC | **0.883±0.062** | 0.00116 | **0.771±0.020** | **0.039** | **0.861** |

### WebShop (decision / cost)

| Method | Success | Cost | HV | IGD ↓ | PSS |
|--------|---------|------|-----|-------|-----|
| B0 Random | 0.406±0.042 | 0.0036 | 0.119±0.006 | 0.075 | 0.602 |
| B1 ReAct | 0.200 | 0.0039 | — | 0.342 | — |
| B2 NSGA-II | 0.411±0.052 | 0.0038 | 0.210±0.065 | 0.068 | 0.604 |
| B3 NSGA-III | 0.406±0.042 | 0.0036 | 0.119±0.006 | 0.075 | 0.602 |
| **B4 +PEEM** | **0.500±0.014** | 0.0049 | **0.265±0.008** | **0.054** | **0.637** |
| B5 +PEEM+PPEC | **0.500±0.014** | 0.0049 | **0.265±0.008** | **0.054** | **0.637** |

### Preference shift (WebShop, Fig.2 data)

| Preference | mean perf | mean cost | PSS |
|------------|-----------|-----------|-----|
| accuracy_first | **0.517** | 0.00502 | 0.567 |
| cost_first | 0.417 | **0.00456** | **0.697** |
| balanced | 0.367 | 0.00432 | 0.591 |

---

## 6. Figures (data in `results/benchmark_extension/pareto_curves.json`)

| Figure | Content |
|--------|---------|
| Fig 1 | Pareto (Success vs Cost): NSGA-II / NSGA-III / PEEM / PEEM-PPEC |
| Fig 2 | Preference shift (accuracy vs cost region) |
| Fig 3 | HV evolution curves (WebShop B5) |

## 7. Paper impact analysis

1. **Generality:** PEEM gains hold on **both** ALFWorld and WebShop
   (Success +6 pts / +9 pts vs NSGA-III).
2. **NSGA-II baseline:** NSGA-III ≈ NSGA-II on ALFWorld; PEEM lifts both metrics
   over either backbone — contribution is **memory-based operator learning**, not
   just many-objective ranking.
3. **Cost tradeoff:** WebShop PEEM raises success and HV at higher cost — the
   intended Pareto tradeoff; PPEC can pull toward cheaper regions (Fig.2).
4. **Statistics:** all main cells are 3-seed mean ± std under **equal budgets**.

### Recommended claim

> PEEM-PPEC is a **general** many-objective evolutionary framework for
> adaptive LLM agents across planning (ALFWorld) and decision/cost (WebShop)
> environments, improving success and Pareto quality at equal evaluation budget.

## 8. Reproduce

```bash
python experiments/run_benchmark_extension.py
python -m pytest -q
```

Artifacts: `results/benchmark_extension/{alfworld_final,webshop_final,nsga2_comparison,pareto_curves,summary}.json`
