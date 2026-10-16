# Stage 1.7-R1 Action Relevance Audit

Evidence: `results/stage1_7_r1/action_relevance_tests.json`.

| Rule | Test |
|---|---|
| Target pickup ranks first over unrelated | `test_target_pickup_ranks_above_unrelated` |
| Candidates ⊆ admissible | `test_candidates_subset_of_admissible` |
| Empty admissible → GROUNDING_BLOCKED | `test_grounding_blocked_empty_admissible` |
| Truncation keeps the unique target action | `test_candidate_truncation_keeps_target_action` |

## C1 tool location

`LOCATE_TOOL` is satisfied when admissible actually contains `use <tool> …`
(or light already on) — not when a location string matches a lamp name.

## C3 truncation

`Legal Action Candidates` = top 12 by relevance (target-object match dominates).
The LLM still sees up to 40 raw admissible commands and may pick any of them;
parser cannot execute a non-admissible command.

## C4 planner does not override LLM

Planner only sorts/annotates. `select_action` still uses LLM text + the
unchanged parser/fallback. No expert sequences. No game_id maps.
