# Candidate Lineage and Feedback Record Schema

## Lineage record (per candidate)

```json
{
  "id": "R|F|E2|P",
  "program_id": "wfp-…",
  "parent_program_id": "wfp-…|parent-frozen-0001",
  "generation": 0,
  "operator_history": ["ROOT_PARENT", "M_SET_INSTRUCTION"],
  "operator": "OP_ARITH_RECHECK",
  "params": {"instruction_pool_index": 0},
  "seed": 20260603,
  "slot": 0,
  "instruction_sha256": "…",
  "graph_sha256": "…",
  "parent_graph_sha256": "…",
  "status": "SUCCESS|FAILED",
  "reason": "…",
  "selection_reason": "policy[ANSWER_MISMATCH] -> OP_ARITH_RECHECK",
  "feedback_label": "ANSWER_MISMATCH"
}
```

## FailureRecord

```json
{
  "task_id": "gsm8k-train-XXXX",
  "parent_program_id": "wfp-…",
  "parent_graph_sha256": "…",
  "success": false,
  "error_category": "ANSWER_MISMATCH|EXECUTION_ERROR|PARSE_ERROR",
  "predicted": "…",
  "gold": "…",
  "diagnostic": "host-side only",
  "diagnosis_uses_gold": true
}
```

## FeedbackSummary

```json
{
  "coarse_label": "ANSWER_MISMATCH",
  "rationale": "…",
  "eligible": true,
  "n_records": 1,
  "records": ["…FailureRecord"]
}
```

**Invariant:** gold never appears in candidate solve prompts.
