# Phase 0 Final Audit

**Date:** 2026-02 (repo `D:\新建文件夹`, branch `main`)  
**Scope:** Agent Genome · NSGA-III authenticity · Pareto selection · tests · demo reproducibility  
**Method:** source inspection + executable audit script `docs/_phase0_audit_checks.py` + `pytest`

## Verdict

**PASS** — 37/37 audit checks and 47/47 unit tests.

One critical defect was found and fixed before finalization (see Finding 1).
Result images were not modified by this audit.

---

## 1. Agent Genome

| Check | Result |
|-------|--------|
| `to_dict` / `from_dict` round-trip | PASS |
| `to_json` / `from_json` round-trip | PASS |
| stable `key()` for dedup/sort | PASS |
| `replace()` immutability (original unchanged) | PASS |
| comparable (`__eq__` / `__lt__`) | PASS |
| rejects unknown strategy | PASS |
| rejects out-of-range `reasoning_budget` | PASS |
| budget bounds valid (`8..128`, step 8) | PASS |
| `Individual` JSON round-trip | PASS |
| `Individual.clone(reset_id=True)` | PASS |

**Fields:** `planner_strategy`, `memory_strategy`, `reflection_strategy`, `tool_policy`, `reasoning_budget`  
**Contract:** serializable, comparable, mutable via `replace` / operators — satisfied.

---

## 2. NSGA-III is a real implementation

Import scan of `src/evolution/nsga3.py`: only stdlib + `src.agent.individual` + `src.evaluation.objectives`.  
**No** `pymoo` / `deap` / `platypus` / other black-box MOEA library.

| Algorithm piece | Symbol | Result |
|-----------------|--------|--------|
| Fast non-dominated sorting | `non_dominated_sort`, `dominates` | PASS |
| Reference direction generation (Das–Dennis) | `generate_reference_directions` | PASS |
| Normalization (ideal + intercept nadir) | `normalize_fitness` | PASS |
| Association (perpendicular distance) | `associate_to_references`, `_perpendicular_distance` | PASS |
| Niching selection (Jain min-count + random tie-break) | `niching_select` | PASS |
| Environmental selection API | `NSGA3.select` | PASS |

Reference-direction cardinality matches `C(H+M-1, M-1)`:

| M | H | expected | actual |
|---|---|----------|--------|
| 3 | 2 | 6 | 6 |
| 5 | 2 | 15 | 15 |
| 5 | 3 | 35 | 35 |

Many-objective support verified for **5 / 6 / 8** objectives (`NSGA3(..., maximize=...)`).

---

## 3. Pareto selection

| Check | Result |
|-------|--------|
| Objective order `[performance, efficiency, cost, robustness, autonomy]` | PASS |
| `to_minimization` signs (`cost` stays positive, others negate) | PASS |
| Mixed-direction dominance (`dominates_mixed`) | PASS |
| Algorithm front size == brute-force `filter_pareto_mixed` | PASS |
| Front members are non-dominated | PASS |
| Min-space front indices == mixed-space front indices | PASS |
| Toy evaluator tradeoff exists (cheap vs strong do not dominate) | PASS |
| Toy evaluator deterministic + 5 objectives in `[0,1]` | PASS |

### Finding 1 (fixed) — objective sign bug

**Severity:** Critical  
**Where:** `NSGA3.select` / `sort_fronts` / `pareto_front` ranked raw paper-semantics
fitness with pure minimization.

**Effect:** `performance`, `efficiency`, `robustness`, `autonomy` were optimized in the
**wrong direction** (only `cost` was correct). Example regression:

```text
A = [0.9, 0.5, 0.2, 0.5, 0.5]   # better performance, better cost
B = [0.5, 0.5, 0.5, 0.5, 0.5]

correct mixed dominance: A dominates B  -> True
old min-on-raw:          A dominates B  -> False  (treated as tradeoff)
```

**Fix:**

1. `src/evaluation/objectives.py` — `to_minimization(..., maximize=)` supports
   custom sign masks; 5-objective default keeps paper semantics.
2. `src/evolution/nsga3.py` — `to_min_matrix` + `NSGA3(maximize=...)`;
   selection/sorting convert before dominance.
3. `src/utils/pareto.py` — `dominates_mixed` / `pareto_mask_mixed` / `filter_pareto_mixed`.
4. `src/evolution/population.py` — history non-dominated count uses converted fronts.
5. Regression tests: `test_dominates_mixed_respects_cost_direction`,
   `test_nsga3_prefers_higher_performance_same_else`, rewritten elite-selection test.

---

## 4. Tests

```text
python -m pytest -q
47 passed
```

| Suite | File | Covers |
|-------|------|--------|
| Genome serialization | `tests/test_genome_serialization.py` | JSON/dict round-trip, validation, comparison |
| Individual | `tests/test_individual.py` | round-trip, clone |
| Mutation | `tests/test_mutation.py` | prompt/memory/reflection/tool/budget + crossover |
| Population | `tests/test_population.py` | initialize/add/select/next_generation, determinism |
| NSGA-III | `tests/test_nsga3.py` | sorting, reference dirs, niching, elite keep, ≥5 obj |
| Pareto | `tests/test_pareto_front.py` | mixed dominance, front vs brute force, evaluator |

Required acceptance cases (serialization / mutation / population / NSGA-III /
Pareto) are present and passing.

---

## 5. Demo reproducibility

Command: `python experiments/run_nsga3_demo.py`

| Check | Result |
|-------|--------|
| Same seed twice → identical `pareto_front.json` | PASS (`hash=07a1acd6b1dd`) |
| Writes `results/population_history.json` | PASS |
| Writes `results/pareto_front.json` | PASS |
| Writes objective visualization | PASS (`objective_scatter.png`) |
| Writes `results/run_summary.json` | PASS |
| Default run (`pop=60`, `gens=25`, `seed=42`) | PASS |

Committed `results/*` artifacts were **left untouched** by this audit
(per instruction not to keep modifying result images).

---

## Commands to re-run

```bash
python -m pytest -q
python docs/_phase0_audit_checks.py
python experiments/run_nsga3_demo.py
```

## Phase 1 readiness

Algorithmic foundation is sound after Finding 1. Safe to plug a real LLM
evaluator behind `EvaluateFn` without changing NSGA-III / Population contracts.

**Waiting for Planner to publish Phase 1.**
