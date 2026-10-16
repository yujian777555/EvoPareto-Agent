# Scientific Validity Audit (Stage 2.0-R1)

**Base commit:** `5fa44ab` · **Real LLM calls: 0**

## P0 repairs

| P0 | Issue | Fix |
|---|---|---|
| P0-1 | task_id collision (all `FAULT_*` prefix) | `fault~seed~index` + opaque `policy_task_id()`; template-grouped splits |
| P0-2 | static fault→reward lookup | real `WorkflowInterpreter` — nodes mutate state; reward from independent evaluator |
| P0-3 | shuffled control unstable | deterministic seed-derived permutation; UNKNOWN_ONLY & WRONG_DIAGNOSIS modes |
| P0-4 | heldout leakage | Protocol A frozen (no updates) vs Protocol B online (reported separately) |
| P0-5 | broken oracle | exact enumeration over operator sequences (budget=3) |
| P0-6 | genome reuse across tasks | Experiment-1 paired per-task parent/child; fresh `base_genome()` per task |

## Math contract

`objective_improvement` dimension-aware (2-obj → `candidate_2obj` maximize/minimize).

## Invalid tests

Removed `or True` in `tests/fceol/test_fceol_core.py`.
