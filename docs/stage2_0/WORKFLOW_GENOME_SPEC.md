# Workflow Genome Spec

`src/research/fceol/workflow_genome.py` — restricted executable structure.

Nodes: GENERATE · VERIFY · DIAGNOSE · REPAIR · ROUTE · SUBMIT.
Edges: directed, must keep SUBMIT reachable from GENERATE on enabled nodes.
Params: max_repairs ∈ [0,3], context_mode ∈ {full,truncated,none},
route_policy ∈ {direct,verify_first}.

API: serialize / deserialize / validate / hash / clone / enabled_kinds.

## Mutation operators (structural, testable)

| ID | Edit | Effect |
|---|---|---|
| M1_INSERT_VERIFICATION | GENERATE→VERIFY→… | adds real verify step |
| M2_ADD_FAILURE_RECOVERY | DIAGNOSE→REPAIR→GENERATE loop | adds recovery, bumps max_repairs |
| M3_CHANGE_TOOL_ROUTING | toggle route_policy (+ROUTE node) | changes routing behavior |
| M4_MODIFY_CONTEXT_FLOW | cycle context_mode | changes context passing |

Invalid edits return None (never corrupt the genome). Evaluator is not a
genome field — cannot be mutated.

## Phenotype

Different structures change `observable_symptoms` and `EvalResult.reward`
in `controlled_faults.ControlledEnv` — real execution semantics, not labels.
