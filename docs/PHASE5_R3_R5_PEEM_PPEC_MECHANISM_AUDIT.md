# Phase5-R3-R5 — PEEM / PPEC Mechanism Audit

Offline only (`results/phase5_r3_r5/peem_ppec_offline/mechanism.json`).

## PEEM

- utility updates from fitness records → sampling probability **changes**
  (planner 0.200 → 0.216 after high-MV credit).
- all-zero-success case: cheap-fail `budget` does not explode over `planner`
  (`budget_not_dominant=True`) — decay + prior limit collapse.
- credit comes from evaluation protocol vectors only (no gold leak).

## PPEC

- accuracy vs cost preferences → **different** selected individuals.
- reference direction sets **differ** under two preference vectors.

## Attribution rules (prereg)

| comparison | claims |
|------------|--------|
| RS vs NSGA-III | selection value |
| NSGA-III vs +PEEM | operator learning |
| +PEEM vs +PEEM+PPEC | preference search |
| optional NSGA-III+PPEC | isolate PPEC without PEEM |

Do not credit PEEM+PPEC joint gains to both independently.
