# Closest Papers Method Comparison

## DAGO (2610.05284)

- Search: LinUCB contextual bandit over **parent-fusion arms**; DAG lineage.
- vs AFlow: replaces MCTS-style sampling with bandit-guided multi-parent
  fusion; claims 81.7 vs AFlow 80.3, −11.2% cost. `FULL_TEXT_NOT_VERIFIED`.

## GEPA (referenced as baseline in 2610.14977 / 2610.15055 / 2610.14662)

- Reflective mutation + Pareto candidate selection + candidate merging
  (per citations). Used as strong prompt-evolution baseline.
  `FULL_TEXT_NOT_VERIFIED` (primary GEPA paper not fetched this session).

## CoCoEvolve (2610.12794)

- Meta-reflection mutator retrieves full evolutionary history + probes live
  system before proposing edits. Already does active probing — relevant to
  any "diagnose-before-mutate" idea. `FULL_TEXT_NOT_VERIFIED`.

## "Does Failure Feedback Direct Agent Self-Modification?" (2610.14662)

- Empirical: 145 DGM modifications show **no target-specific repair
  advantage**; target feedback helps only with identifiable, repairable
  mechanisms. Directly bounds what failure information can buy.
  `FULL_TEXT_NOT_VERIFIED`.

## HarnessEvolve / HarnessCompass / ADAS / AgentSquare

- Named in brief; **REFERENCE_UNVERIFIED** for precise methods this session.

## Consequence

Naive "AFlow + failure diagnosis" or "GEPA + skill memory" = module
combination, not a contribution. Any gap must live **inside** search
decisions (parent choice, credit, acceptance) with evidence from real traces.
