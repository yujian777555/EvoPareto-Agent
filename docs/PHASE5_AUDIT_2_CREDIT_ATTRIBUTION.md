# Phase5-Audit-2 — PEEM Credit Attribution

**Priority:** P0 · **Status:** COMPLETE (honest limitations documented) · **Algorithms:** unchanged

## Question

Does PEEM learn **(A) true mutation-operator contribution**, or merely
**(B) correlation with successful offspring**?

## Method

1. **Observational:** aggregate `EvolutionRecord`s from a PEEM run by
   `mutation_type` → mean improvement + bootstrap 95% CI.
2. **Counterfactual (do-intervention):** for each of 20 parents, apply *every*
   mutation type 3× and measure Δobjective / Pareto-dominance rate.
3. Compare rankings (`attribution_verdict`).

## Results (`results/audit/credit_attribution.json`)

### Observational ranking (by mean improvement)

1. reflection · 2. planner · 3. tool · 4. budget · 5. memory

### Counterfactual ranking

1. **planner** (μ=0.035, CI [0.030, 0.040]) 
2. **tool** (μ=0.025, CI [0.009, 0.042], Pareto-dominance 0.57)
3. budget · 4. memory · 5. reflection (≈0 / null CIs)

### Verdict

| check | result |
|-------|--------|
| top-1 agreement | **false** |
| causal claim supported | **false** |
| interpretation | observational credit is **partially confounded** |

## Answer

PEEM’s composite MV is **by construction correlated** with offspring outcomes
(improvement + survival terms). Counterfactual intervention shows the operators
with **true positive Δobjective** are `planner` and `tool`; `reflection` ranks
high observationally but is a null intervention on this landscape.

→ **We do not claim full causal identification.** PEEM is a
credit-assignment heuristic; its score is a mixture of signal and
survivorship correlation.

## Limitations (must appear in the paper)

1. Observational MV mixes improvement / pareto bucket / diversity / survival —
   inherently correlational.
2. Counterfactual probe uses a toy evaluator and 20 parents (not full LLM).
3. Bootstrap CIs cover per-transition *improvement*, not the full MV.
4. Top-1 disagreement ⇒ treat PEEM as *useful search bias*, not identified
   causal effect.

## Suggested paper phrasing

> PEEM estimates mutation utility from Pareto-aware outcomes. A counterfactual
> probe indicates the dominant *interventional* operators are planner/tool
> mutations; observational rankings can be confounded by survivorship. We
> therefore describe PEEM as robust operator-utility *estimation* rather than
> causal effect estimation.
