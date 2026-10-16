# Planner Handoff (Stage 2.0-R1)

## Status

**`OFFLINE_VALID_BUT_NO_BENEFIT`**

The offline environment is now valid (real interpreter, unique IDs,
template-split, frozen vs online protocols, exact oracle). Under this valid
protocol, **failure-conditioned operator learning does not beat global AOS or
standard contextual bandit** (all 0.200 frozen mean reward).

## What changed vs Stage 2.0

- Task IDs unique; splits template-isolated.
- Real node execution + independent evaluator (no fault→reward lookup).
- Deterministic shuffled / unknown / wrong-diagnosis controls.
- Frozen transfer (no held-out updates) vs online adaptation separated.
- Exact enumeration oracle (0.384 ceiling vs 0.200 policy).
- Removed invalid `or True` assertions; math contract dimension-aware.

## Honest answer to the core question

> In a real-execution, strictly isolated environment, does failure-conditioned
> operator learning still work?

**No measurable advantage** was found. The earlier Stage 2.0 "+0.159 Δ" was an
artifact of the invalid protocol. Having *good* evidence helps slightly vs
shuffled/unknown, but a conditioned policy is interchangeable with plain UCB
over operators.

## Recommendation for next step

1. **Do not** request real-agent pilot for FCEOL as-is.
2. Either (a) sharpen the mechanism (e.g. richer failure features, deeper
   credit, longer budgets) and re-test offline, or
3. (b) **STOP_RESEARCH_DIRECTION** if a second valid offline attempt also
   fails to beat contextual bandit.

**FINAL_DECISION: OFFLINE_VALID_BUT_NO_BENEFIT**
