# Phase5-R3-R2 — Data Split & Baseline Audit

## Native splits (official ALFWorld)

| split | path | use |
|-------|------|-----|
| valid_train | `/data/json_2.1.1/valid_train` | train-like |
| valid_seen | `/data/json_2.1.1/valid_seen` | eval ID |
| valid_unseen | `/data/json_2.1.1/valid_unseen` | **held-out OOD test** |

Pilot used `valid_unseen` only. Game instance IDs = directory paths (unique).

## Schema isolation

`fail_closed_cross_benchmark` + `validate_episode_schema` prevent injecting
`real_world_agent` catalog into native adapters.

## Baseline plan

| arm | implementation |
|-----|----------------|
| Random Search | **gap:** still loop mutation + NSGA-III; true RS arm TODO |
| NSGA-III | `use_adaptive=False` |
| NSGA-III+PEEM | `robust_peem` |
| +PPEC | `robust_peem` + preference |

Budget: `BudgetManager` API/step/cost gates; pre-reserve concurrent.

## Classification

| kind | meaning |
|------|---------|
| real_environment | native `won` (pilot) |
| real_llm_proxy | LLM + synthetic scoring |
| simulated | mock LLM |
