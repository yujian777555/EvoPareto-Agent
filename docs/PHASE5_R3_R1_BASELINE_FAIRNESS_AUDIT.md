# Phase5-R3-R1 — Baseline Fairness Audit

## Method wiring (code evidence)

| label | implementation | evidence |
|-------|----------------|----------|
| B1 / Random / NSGA-III | `use_adaptive=False`, `experience_mode="phase2"` + NSGA-III select | `MemoryEvolutionConfig`, `MemoryEvolutionLoop` |
| B2 NSGA-III+PEEM | `use_adaptive=True`, `experience_mode="robust_peem"`, `preference=None` | same loop class |
| B3 PEEM+PPEC | `robust_peem` + `preference=...` | `PreferenceAwareNSGA3` replaces selector only |

Random vs NSGA-III: both use random mutation when `use_adaptive=False`; the
evolutionary *selection* is NSGA-III in `MemoryEvolutionLoop`. A pure
random-search (no selection) control is **not** separately implemented — noted
as fairness gap (same as Phase 5-Pre).

## Budget accounting

- Pre-request gate: `assert_budget_before_calls` (before any API call).
- Budget metric in loops: `pop * (gens + 1)` genome evaluations.
- **Gap:** live API/step counts are not yet the primary budget unit.

## Data splits

- Content-level: `task_fingerprint` train/test split (`task_split.py`).
- Leak detection must pass (`detect_task_leakage`) or protocol returns `BLOCKED`.

## Objective / metrics

- Objective signs: fixed Phase 2.5 (`to_minimization`).
- HV / IGD: shared cross-method reference front in ablations.
- Preference: `preference_satisfaction` (cost minimized inside).

## Prohibited practices (verified absent)

- Mock results filling real-environment tables — labeled `simulated` / `real_llm_proxy`.
- Test results used for training-time tuning — not done (fixed configs).
- Capability-prior cited as native success — labeled PROXY.

## Remaining fairness gaps

1. No true pure Random-Search arm (no selection).
2. API/step budget not yet equalized across methods in live runs.
3. Native env missing → all current “real” numbers are proxy or simulated.
