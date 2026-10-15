# R2-R1 — PPEC Validation

Same pool + NSGA-III core; different `Preference2DController` directions.

- success_first / cost_first / balanced — weights frozen
- directions differ; strength=0 → uniform
- environment selection via `loop.nsga3` (not overwritten in pipeline)
- Pareto dominance preserved (dominated points cannot win on score alone)
- cost scale for PSS: fixed clip to [0,1] on USD; HV uses raw USD + fixed ref

Full-loop proof: `test_ppec_env_selection_changes_population`,
`test_ppec_selector_not_overwritten`.
