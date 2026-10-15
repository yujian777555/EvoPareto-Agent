# Phase5-R3-R5 — Initial Audit

**HEAD `9ebddc6`** (= origin/main) · tests green

## Confirmed P0

| id | issue | fix |
|----|-------|-----|
| A1 | `_settle` never released `reserved_cost` | ticket-based pending cost released on settle |
| A2 | nested retries bypass physical counts | `bump_physical_http` in `post_json` per send |
| A3 | cost reserve vs spend invariant | `reserved+spent <= max_cost` enforced |
| A4 | `git_sha=unknown`, `requested_split=null` | metadata path (runner + env meta) |

## Objectives

legacy 5-obj invalid for efficiency/robustness/autonomy → candidate evaluators
`legacy_5obj` / `candidate_5obj` / `candidate_2obj` in
`src/evaluation/objective_candidates.py`.
