# Novelty Gap Review (Stage 3.0-P1)

## Status: `NOVELTY_GAP_ESTABLISHED: NO (hypothesis only)`

| Candidate | Closest prior | EA mechanism relevance | Verdict |
|---|---|---|---|
| Semantic experience credit for workflow evolution | CoCoEvolve; classic credit assignment | **high** (changes parent/mutation decisions) | promising but unproven |
| Diversity-aware parent selection vs AFlow top-k | DAGO LinUCB; QD literature | **high** (search core) | promising but unproven |
| Diagnose-before-mutate | 2610.14662, EnactOpt, CoCoEvolve probes | medium | HIGH_COLLISION |
| Activation-aware inheritance | VaG 2608.05810, LAGO | medium | HIGH_COLLISION |

## Why not yet a gap

Limitation impact requires **real search traces** (absent in official repo).
`REAL_TRACE_EVIDENCE_INSUFFICIENT` → cannot claim any empirical novelty.

## What would confirm a gap

Level-3 pilot capturing: duplicate-modification rate, invalid-candidate rate,
score trajectory, diversity of selected parents, per-modification before/after
scores. Then test whether semantic credit or diversity pressure beats AFlow
selection at equal evals — with DAGO as strong alternative baseline.

**Do not name a new algorithm until that evidence exists.**
