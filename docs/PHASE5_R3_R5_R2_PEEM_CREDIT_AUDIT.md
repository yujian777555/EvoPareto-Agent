# Phase5-R3-R5-R2 — PEEM Credit Audit

`objective_improvement(..., spec=)` — cost index from `ObjectiveSpec`, no `i==2`.

- cost↓ → positive credit (2D)
- success↑ → positive credit
- trade-off → mixed gain (not dominate)
- multi-generation all-zero success: cost-fail gains stay bounded (decay+prior);
  **signal-degenerate** flag documented; raw Plan B not altered.

Operators: AdaptiveMutationController samples from PEEM scores; recordable
per generation via `probability_distribution()`.
