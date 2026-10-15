# R2-R2 — PPEC Selection

## Fail-able test

Conflict front of 5 non-dominated points; select 2 via niching.

**`success_first` vs `cost_first` survivor sets must differ** — assertion can fail.

Observed: sets differ (niching geometry); exact members depend on reference
directions + crowding. Dominated points cannot outrank dominators.
`strength=0` matches uniform NSGA-III. Loop selector identity preserved.

## Note

Single-argmax selection is not enough; PPEC acts through **reference-directed
niching** in environmental truncation. That is the verified mechanism.
