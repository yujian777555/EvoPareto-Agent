# Metric Contract

**Primary:** frozen held-out **mean_final_reward** (per task, after up to 3
paired interventions; task is the statistical unit).

**Secondary:** task_success_rate (reward>0.55) · mean_paired_delta ·
improvement_prob · negative_rate · operator distribution.

Statistics: 10 seeds; mean ± 95% CI over seeds; paired differences
(fceol − baseline) reported explicitly.

**Not used as primary:** single-step Δ (correlated within task), success rate
alone (floor effects here).

Objective directions: performance↑ cost↓ via `SPEC_2`; hypervolume tests in
`tests/fceol/test_math_contracts.py`.
