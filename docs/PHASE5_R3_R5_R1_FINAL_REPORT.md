# Phase5-R3-R5-R1 — Final Report

## 1. Git

Commit this SHA · origin/main · clean · **zero real API calls this phase**.

## 2. HTTP gate

Pre-send SQLite approval; reserved_cost settles to 0; 402 fail-fast; tests cover
fallback/timeout/multiprocess/persist.

## 3. 2D NSGA-III

`maximize=(True, False)`; A≻B, A≻C, A∥D verified in sort/credit.

## 4. NSGA-II

Independent baseline class with crowding + tournament.

## 5. PEEM 2D

ObjectiveSpec-driven improvement (cost index explicit); legacy 5-obj intact.

## 6. PPEC 2D

success_first / cost_first / balanced; real 2D fitness (no 5D pad).

## 7. 2D evolution loop

`run_2d_evolution` smoke: spec `[performance, cost]`, front non-empty.

## 8. All-zero success

Documented degeneracy (cheap-fail preference). Feasibility-first **not** auto-applied.

## 9. Prereg

Arms A–F, equal budgets, dual resource views — awaiting Planner.

## 10. Tests

Host pytest **all green** (2D dominance, credit spec, PPEC 2D, HTTP gate, NSGA-II).

## Research answers (brief)

1. 2D NSGA-III math: **correct** (dominance + maximize mask).  
2. NSGA-II necessity: **yes** as 2D baseline (NSGA-III degenerates).  
3. PEEM: updates sampling from spec-aware credit.  
4. PPEC 2D: meaningful preference regions.  
5. All-zero: cost-preference degeneracy (expected).  
6. Cheap-fail: **yes** if all success=0 — gated as degeneracy.  
7. Native PEEM signal: sparse; needs multi-episode.  
8–10. Ready for **approved** live pilot after Planner freeze.

## Final status

**`ACCEPTED_2D_PROTOCOL_READY`**
