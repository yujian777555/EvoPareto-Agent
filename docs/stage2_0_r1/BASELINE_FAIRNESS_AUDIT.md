# Baseline Fairness Audit

All policies in Experiment-1 (operator learning):

- start from the **same** `base_genome()` per task
- same task list, same steps_per_task=3, same operators
- same interpreter + independent evaluator
- freeze_policy=True on held-out (Protocol A)

Baselines: random · global_aos · fixed_map · contextual_bandit · fceol ·
shuffled · unknown_only · wrong_diagnosis · oracle.

**FCEOL vs contextual_bandit:** both are UCB over context keys; FCEOL only
widens exploration for `ctx:UNKNOWN`. If they tie, the failure-conditioning
mechanism (beyond having a context) adds no value.

Online adaptation (Protocol B) reported separately — cannot replace frozen
transfer.
