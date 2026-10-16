# Hypotheses & Falsifiability

All metrics defined before experiments; no post-hoc metric swapping.

## H1 — Experience Efficiency
**Claim:** PEEM (Pareto-credit operator memory) reaches equal HV with fewer
real evaluations than plain NSGA-II/III and than bandit-AOS.  
- **Vars:** HV(AUC vs evals), evals-to-target-HV, operator distribution JS.  
- **Controls:** NSGA-II, NSGA-III, NSGA-II+UCB-AOS, +Archive-replay.  
- **Effect threshold:** ≥20% fewer evals to 95% of final HV (practical), across
  ≥3 of 5 seeds.  
- **Falsified if:** CI includes 0 or AOS baseline matches/beats PEEM.  
- **Confounders:** genome space size, noise, budget accounting.  
- **Anti-cherry-pick:** primary metric HV-AUC frozen; all others secondary.

## H2 — Preference Adaptation
**Claim:** dynamic PPEC (front/budget-tracking) improves coverage of the
preferred region vs fixed weights and vs no preference, without losing
global HV by more than 10%.  
- **Vars:** preferred-region HV, IGD+ to preference reference, global HV.  
- **Controls:** no-PPEC, fixed-weight PPEC, ParEGO-style scalarization.  
- **Threshold:** ≥15% preferred-region HV gain at ≤10% global HV loss.  
- **Falsified if:** fixed weights match dynamic, or global HV collapses.  
- **Confounders:** preference schedule; reference-point construction.

## H3 — Joint Benefit
**Claim:** PEEM+PPEC interaction (2×2 factorial) yields super-additive
benefit on anytime HV under hard API budget.  
- **Vars:** HV(AUC), cost per non-dominated solution, interaction contrast.  
- **Controls:** PEEM only, PPEC only, neither, archive-replay+fixed-pref.  
- **Threshold:** interaction term positive on ≥3/5 seeds with bootstrap 90% CI>0.  
- **Falsified if:** additive-only or negative interaction.  
- **Confounders:** tuning cost asymmetry (must budget equal hyperparameter
  search for all arms).

## Optional H4 — Budget-gated robustness
Under enforced physical-HTTP caps, experience-guided allocation keeps
feasibility (no BillingBlocked) more often than uniform sampling.  
Threshold: ≥50% fewer budget aborts at same cap. Keep only if H1 shows signal.
