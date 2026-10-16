# Novelty / Collision Matrix

| Our claim | Nearest prior | Type of collision | Severity | Survivable? |
|---|---|---|---|---|
| Multi-objective LLM-agent optimization | MOAE, Harmony Harness, RoboPhD | **mechanism + application** | HIGH | only with sharp new mechanism |
| Experience-guided agent evolution | RSI-Router, MAPLE, EvoDrive | name + method similar | VERY HIGH (RSI-Router) | risky |
| Performance–Cost Pareto | CRAFT, MO-CAPO, RSI-Router, RoboPhD price points | **same objective pair** | HIGH | common axis; need unique mechanism |
| PEEM operator memory | classic AOS; MOAE archive | **component rebranding** | HIGH | rename/reframe; add real delta |
| PPEC preference adaptation | NSGA-III/RVEA preference literature; CRAFT's anti-fixed-weight argument | **known family** | HIGH | only if truly dynamic |
| Budget-aware search under API caps | CRAFT (validation-as-scarce), RoboPhD (tight eval budgets) | method-near | MEDIUM | engineering-strong angle remains |
| NSGA-III as headline | standard | not novel | n/a | baseline only |

## Name-collision vs method-collision

- **Name similar, method different:** "PPEC" vs ParEGO/PEA literature — different
  surface, same *preference-biased selection* idea.
- **Method similar, application different:** EvoDrive (driving scenarios) vs
  agents — same Pareto-archive+memory pattern.
- **True duplicate risk:** MOAE / RSI-Router already do Pareto agent evolution
  with experience and cost; publishing the same story is not viable.

## What would actually differentiate

1. **Dynamic** preference that tracks front/budget (not 3 frozen presets).
2. Operator utility that **changes mutation distribution** and transfers
   across tasks — measured against bandit AOS.
3. Strict **physical-evaluation budget** optimization as the scientific
   object (not a footnote), with anytime HV curves.
4. A **3-objective** setting (perf, cost, robustness/latency) where NSGA-III
   is the right tool and PPEC's reference adaptation is load-bearing.
