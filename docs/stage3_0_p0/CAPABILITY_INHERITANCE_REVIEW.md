# Capability Inheritance Review (Candidate B)

## Question

When evolution adds a capability, does the next generation actually activate,
use, and keep it?

## Evidence from literature (already published)

| Work | What it does |
|---|---|
| **2608.05810 VaG** | skill-contamination phase transition; pre-commit 3-critic gate; marginal-gain selection |
| **2605.08887 Ace-Skill** | clustered knowledge; prioritized rollouts; transfer to smaller models |
| **2610.19843 LAGO** | growing options library; ablation shows library matters |
| **2610.14216 Cortex** | A/B measurement gate for harness rules |
| Harmony Harness | factorized transferable vs env-specific harness parts |

## Decomposition (our E1)

Capability Added → Reachable → Activated → Executed Correctly → Performance
Improved → Regression Avoided. VaG handles admission; LAGO handles reuse;
**activation vs mere presence** is only partially covered.

## Gap status

Skill admission / contamination / gating is **published**. A finer
"activation-aware inheritance" (does the added module ever fire correctly?)
is a modest increment, not a clear algorithmic breakthrough.
**HIGH_COLLISION_RISK** if framed as "skill memory" or "gating".
