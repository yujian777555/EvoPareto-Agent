# Oracle Definition

`OracleBest.plan` — **exact enumeration** of operator sequences up to
`budget` steps from the same `base_genome()`, evaluating each via the same
`eval_genome`. Returns argmax final reward.

Not a repeat-one-operator heuristic. Handles idempotent ops (clone), invalid
ops (skip), and optimal early stop (best prefix recorded).

**Ceiling property:** with same initial state, task, budget and reward,
`oracle_best_final_reward ≥ any policy's final reward`.

Observed (budget=3, held-out): oracle mean **0.384** vs best policy 0.200 —
proves better sequences exist that policies fail to find; oracle is a true
upper bound here.

Distinction: oracle bounds **final reward**, not mean paired Δ.
