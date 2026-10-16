# Experiment Design (Formal Arms)

## Arms (minimum)

1. Random Search  
2. NSGA-II  
3. NSGA-III *(only if M≥3; else demote to baseline with justification)*  
4. NSGA-III/II + PEEM  
5. NSGA-III/II + PPEC (dynamic)  
6. + PEEM + PPEC  
7. **Controls:** Archive Replay; fixed-weight preference; bandit-AOS; no-adaptive.

## Fairness (frozen)

Same genome space · same splits · same model · same evaluation budget (real
HTTP/tokens/dollars) · same seeds protocol · same cost accounting · no test-
set feedback · equal hyperparameter search budget per arm.

## Metrics

- Primary: **anytime HV** vs real evaluations; HV(τ) at fixed budget τ.
- Secondary: success rate, cost/success (undefined if zero), IGD+ (with
  declared reference set), attainment curves, stability across seeds.
- 2-D note: if M=2, **report NSGA-II** as first-class; NSGA-III extra only.
- Noise: ≥5 seeds; bootstrap CIs; never equate HV delta with significance.

## Environment

**Primary: EvalPlus (HumanEval+/MBPP+)** with pass rate + token cost.  
**Secondary: BFCL** if tool-policy genes retained.  
ALFWorld: regression-only.

## Shared runtime rules

All arms use the same agent execution layer. No PEEM/PPEC-only harness boosts.
Genes must show phenotype differences first (GENOME_PHENOTYPE_REDESIGN.md).
