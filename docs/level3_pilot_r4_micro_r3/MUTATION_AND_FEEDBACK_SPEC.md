# R3 Mutation Operators and Feedback Policy

## A. Random mutation R (seeded operator set)

Operators (`MUTATION_OPERATOR_NAMES` in `src/research/r3_mutation_feedback.py`):

| Operator | Semantic | Implementation |
|---|---|---|
| `OP_INSTRUCTION_STYLE` | instruction style / brevity | `mutate_insert_instruction` |
| `OP_REASONING_ORG` | step organization | `mutate_insert_instruction` |
| `OP_ARITH_RECHECK` | arithmetic verification | `mutate_insert_instruction` |
| `OP_ERROR_RECOVERY` | self-correction clause | `mutate_insert_instruction` |
| `OP_OUTPUT_CONSTRAINT` | output format constraint | `mutate_insert_instruction` |

* Seed: `SEED=20260603` (frozen).  
* `apply_random_mutation(parent, seed, slot)` → deterministic LCG-style `random.Random((seed<<8)^slot)`.  
* Records operator, params, parent/child IDs and graph SHAs.  
* Empty / no-op mutations → `status=FAILED`, child=None (never silent redraw).

**Note:** these operate on the **instruction + compiled graph** (parent graph_source updated via instruction slot). Full structural graph ops (insert node / rewire) remain in `r4_workflow_program.mutate_*` and can be added to the operator set in a later freeze version.

## B. Feedback-driven mutation F

Pipeline: `FailureRecord → FeedbackSummary → MutationPolicy → ChildCandidate`

### FailureRecord fields
`task_id`, `parent_program_id`, `parent_graph_sha256`, `success`, `error_category`, `predicted`, `gold`, `diagnostic`, `diagnosis_uses_gold`

### Coarse labels only (no invented fine-grained causes)
| Label | When |
|---|---|
| `ANSWER_MISMATCH` | predicted ≠ gold (host-side compare) |
| `EXECUTION_ERROR` | harness/LLM exception |
| `UNKNOWN_OR_PARSE` | output unusable |
| `NO_FAILURE` | all success |

Fine-grained claims (arithmetic vs comprehension) are **not** allowed without extra evidence.

### Policy map
| Feedback label | Operators (priority order) |
|---|---|
| `ANSWER_MISMATCH` | `OP_ARITH_RECHECK`, `OP_REASONING_ORG` |
| `EXECUTION_ERROR` | `OP_ERROR_RECOVERY`, `OP_OUTPUT_CONSTRAINT` |
| `UNKNOWN_OR_PARSE` | `OP_OUTPUT_CONSTRAINT`, `OP_INSTRUCTION_STYLE` |
| `NO_FAILURE` / none | `OP_INSTRUCTION_STYLE` or **fail** |

No usable feedback → `build_feedback_child` returns `(None, status=FAILED, reason=NO_USABLE_FEEDBACK)`.

### Leakage boundary
Gold may appear in `FailureRecord` for **host diagnosis only**. `diagnosis_uses_gold=True` is recorded. Gold is **never** concatenated into solve prompts.

## C. Gen-2 E2

1. Select gen-1 parent by **pre-registered** dev rule (max accuracy; tie → fixed order).  
2. Save that parent's FailureRecords → FeedbackSummary.  
3. `build_feedback_child(parent, summary, …)` for E2 (no hardcoded instruction).  
4. Record generation=2, parent_program_id, operator, feedback summary, new hash.  
5. If feedback insufficient → E2 generation **fails explicitly** (counted, not dropped).

## Fair budget

Random and feedback groups share the same operator set, same candidate count, same evaluation budget per candidate. Difference is **only** operator-selection mechanism.
