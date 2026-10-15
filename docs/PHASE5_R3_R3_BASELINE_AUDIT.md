# Phase5-R3-R3 — Baseline Audit

## True Random Search

`src/evaluation/native_evolution_evaluator.py` `RandomSearchSampler`:

- samples `AgentGenome.random`
- **no** NSGA-III selection
- **no** PEEM credit
- **no** PPEC
- archive stores results but **does not** change sampling

Test: `test_random_search_no_nsga3`, `test_random_search_sampling_only`.

## Method matrix (native evaluator)

| Method | selection | mutation |
|--------|-----------|----------|
| Random Search | none | uniform genome sample |
| NSGA-III | NSGA-III | random mutation |
| NSGA-III+PEEM | NSGA-III | PEEM utility |
| NSGA-III+PEEM+PPEC | PreferenceAware NSGA-III | PEEM + preference |

## Fairness

- same native env / game rotation
- same task budget (n_tasks × genomes)
- API usage counted per episode
- train/dev on valid_train; held-out valid_unseen (not used for tuning in micro pilot)

## Remaining gap

Full multi-seed comparison under equal API budget not yet run (budget gate).
