# Novelty Gap Matrix

| Idea | Top-3 nearest | Already done? | Proposed change | Heuristic enough? | Bandit/AOS/MCTS enough? | Fair experiment? | Needs multi-gen? | Public bench? | Negative-value if falsified | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| A: Failure identifiability → diagnose-vs-mutate policy | 2610.14662, EnactOpt 2610.14977, CoCoEvolve 2610.12794 | directedness measured; probe-before-edit exists | explicit identifiability-gated search step | often yes (threshold rules) | bandit/MCTS can encode it | possible | yes | SWE-bench | "identifiability not predictive" | **HIGH_COLLISION** |
| B: Activation-aware capability inheritance | VaG 2608.05810, Ace-Skill, LAGO, Cortex | admission/gating/library published | activation-behavior regression gate | partly (A/B tests) | not central EA | possible | yes | Terminal-Bench 2 | "gate is enough" | **HIGH_COLLISION** |
| C: Multi-objective harness search | Harmony Harness, MOAE | done | — | — | — | — | — | — | — | **REJECT** |
| D: Experience-guided evolution | RSI-Router, MAPLE, CoCoEvolve | done | — | — | — | — | — | — | — | **REJECT** |

**Module combination ≠ contribution.** AFlow+Diagnosis or GEPA+SkillMemory
alone is insufficient. No candidate currently shows a non-replaceable
algorithmic mechanism.

Verdict: `NO_DEFENSIBLE_GAP_FOUND` for direct立项; reproduce AFlow first and
mine *empirical* limitations not covered by the above.
