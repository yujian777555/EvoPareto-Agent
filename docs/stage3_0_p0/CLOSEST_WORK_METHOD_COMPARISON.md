# Closest Work Method Comparison

| Work | Representation | Search | Feedback | Key difference vs our candidates |
|---|---|---|---|---|
| AFlow | code workflow graph | MCTS | execution | no failure-identifiability layer |
| DAGO | DAG lineage | LinUCB fusion | validation | bandit over *parents*, not diagnoses |
| EnactOpt | skills + context code | diagnosis-guided edits | adjacent decisions | already diagnoses evidence-missing vs unused |
| CoCoEvolve | harness edits | meta-reflection | history + live probes | already probes before mutate |
| 2610.14662 | instruction/code mods | observational study | failure feedback | **measures** directedness; no search mechanism |
| VaG (2608.05810) | skill pool | 3-critic gate | skill validation | admission gating done |
| LAGO | options library | retrieve/spawn | sub-task verify | library inheritance done |
| Socratic-SWE | trace→skills | closed-loop tasks | traces | repair-pattern reuse done |

## Takeaway

Candidate A (identifiability) and B (inheritance) both have 2026 papers that
already touch the core. A *search-policy* that explicitly chooses DIAGNOSE vs
MUTATE under measured identifiability is the only thin remaining gap — and
EnactOpt/CoCoEvolve already probe. **HIGH_COLLISION_RISK** for naive claims.
