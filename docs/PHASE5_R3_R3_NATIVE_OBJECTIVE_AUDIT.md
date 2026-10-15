# Phase5-R3-R3 — Native Objective Audit

Paper objectives: performance · efficiency · cost · robustness · autonomy

## Current native measurements (`NativeEvolutionEvaluator.to_objectives`)

| objective | source | native? | circular prior? |
|-----------|--------|---------|-----------------|
| performance | env `won` rate | **YES** | no |
| efficiency | 1/(1+steps/max_steps + tokens/2000) | **YES** (steps+tokens) | no |
| cost | API cost saturating transform | **YES** (usage delta) | no |
| robustness | perf × (1 − stall_rate) | PARTIAL (stall-based) | no |
| autonomy | 1 − 0.5·early_budget_kill − 0.3·stall | **PROXY (behavioral)** | improved vs config-name prior |

## Old definition problems

`ObjectiveEvaluator._autonomy` used reflection/tool/budget **names** → circular.

## Native metric formulas (diagnostic only until Planner approves)

```text
performance = mean(won)
efficiency  = 1 / (1 + mean(steps)/max_steps + mean(tokens)/2000)
cost_score  = c / (c + 1)     # lower raw cost better
robustness  = performance * (1 - stall_rate)
autonomy    = 1 - 0.5*early_budget_rate - 0.3*stall_rate
```

## Limitations

1. robustness not yet across task categories / perturbations.
2. autonomy is a behavioral proxy (fallback/early-stop), not a causal measure.
3. Native metrics are **diagnostic**; formal paper tables await Planner sign-off.

## Verdict

**Not all five objectives fully validated for paper main tables.**
performance/efficiency/cost are native; robustness/autonomy need protocol upgrade.
