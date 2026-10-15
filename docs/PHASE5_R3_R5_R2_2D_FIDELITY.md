# Phase5-R3-R5-R2 — 2D Fidelity

`ObjectiveSpec` candidate_2obj: performance↑, cost↓.

## Dominance A/B/C/D

A(0.9,0.10) ≻ B, A ≻ C, A ∥ D — verified in SPEC_2, NSGA-II `_min_rows`,
NSGA-III maximize mask, PEEM credit (`spec=` param), Pareto front output.

## NSGA-II

Uses `SPEC_2.to_minimization` when dim==2 (crowding on min-space rows).

## NSGA-III

`maximize=(True, False)` on constructor; loop keeps same selector.
