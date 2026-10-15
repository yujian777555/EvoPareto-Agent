# Phase5-R3-R5-R1 — 2D NSGA-III Audit

**Spec:** `candidate_2obj` = (performance ↑, cost ↓)  
`ObjectiveSpec.maximize = (True, False)`

## Dominance cases

| pair | expected | verified |
|------|----------|----------|
| A(0.9,0.10) ≻ B(0.5,0.20) | yes | ✅ |
| A ≻ C(0.9,0.20) | yes | ✅ |
| A ∥ D(0.5,0.05) | non-dominated | ✅ |

Used in NSGA-III fronts, archive, and PEEM credit (via `ObjectiveSpec.improvement`).

## Reference directions

`generate_reference_directions(2, 4)` → **5** Das-Dennis points; unit-sum.

## Normalize / edge cases

- equal success → lower cost wins dominance
- equal cost → higher success wins
- repeated fitness → tie in improvement 0

## NSGA-II baseline

`src/evolution/nsga2_baseline.py` — separate class, crowding + binary tournament;
same Genome/Mutation/Evaluator interface.
