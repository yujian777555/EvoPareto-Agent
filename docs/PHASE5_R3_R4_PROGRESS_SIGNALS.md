# Phase5-R3-R4 — Progress Signals & Positive Control

## Diagnostic signals (not fitness)

`src/evaluation/progress_signals.py`:

- found_goal_object / picked_something / opened_container
- state_changes / repeated_actions / n_steps
- failure taxonomy: budget_exhausted, max_steps, stalled, repeated_action_loop,
  invalid_action, api_failure, environment_error, task_failed, task_success

## Positive control

Attempted on **valid_train** only. `objective_validity.json` records
`positive_control` probe (expert planner path). **Full won=True replay not
completed** this phase (dagger expert_plan extras not exercised in script).

→ Positive control status: **INCOMPLETE** — do not claim evaluator success
recording verified until expert trajectory reaches `won`.

## Forbidden leaks

No gold actions / expert trajectories enter agent prompts (documented in
`positive_control_expectation()`).

## Failure mix (micro history)

Previously: 14× budget_exhausted, 2× max_steps, 0 success.  
FakeLLM horizon: 2× stalled per setting.
