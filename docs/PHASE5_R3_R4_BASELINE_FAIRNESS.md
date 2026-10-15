# Phase5-R3-R4 — Baseline Fairness

| arm | implementation check |
|-----|---------------------|
| Random Search | `RandomSearchSampler` — no NSGA-III/PEEM/PPEC |
| NSGA-III | `MemoryEvolutionLoop` `use_adaptive=False` |
| NSGA-III+PEEM | `robust_peem` utility → mutation probs |
| NSGA-III+PEEM+PPEC | PreferenceAware selector + preference |

Same native evaluator / task pool / budget object `APICallGate`.  
**Not yet:** equal-budget multi-seed native comparison (API 402).

## PPEC selection impact

Offline counterfactual can be run without API (same population →
`select_by_preference` vs fitness0 argmax). Earlier R3 tests show
preference-specific selection differs. Full env-selection A/B on native
fitness remains open.

## Data split

- dev: valid_train (`development_task_pool.json`, 50)
- frozen test: valid_unseen (`frozen_final_test_manifest.json`, 30)
- **contaminated** (seen in pilots): 2 vase→safe game IDs recorded
