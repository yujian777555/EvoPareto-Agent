# Executable Workflow Spec

`WorkflowInterpreter` executes nodes against `ExecutionState`:

| Node | Effect |
|---|---|
| GENERATE | sets `candidate_quality` from task.base_output_quality |
| ROUTE | picks tool via `genome.route_policy`; wrong/broken tool → quality×0.7 |
| VERIFY | quality≥0.55 & constraint → pass; else fail (sabotaged → false pass) |
| DIAGNOSE | infers constraint_missing / wrong_tool / low_quality from feedback & state |
| REPAIR | applies diagnosis-specific fix; miswired recovery → quality×0.9 |
| SUBMIT | marks submitted; independent evaluator scores artifact |

**Genome params wired:** `context_mode` (none → lose constraint; truncated →
partial compensation), `route_policy`, `max_repairs`, enabled nodes.

**Reward** = f(quality, constraint, required_checks) − complexity cost.
No `fault_type` in the reward path.
