# Complete Output Passing Audit (Task A)

## Problem

`run_workflow_code_isolated()` returned `"stdout": proc.stdout[-800:]`. Long
structured results were truncated in the main process BEFORE scoring.

## Fix

1. Full `proc.stdout` is parsed first; only then are diagnostics excerpted.
2. Return interface split:
   - **structured result**: `answer_text`, `answer_len`, `answer_sha256`,
     `cost_meta`, `out_kind`, `task_id`
   - **diagnostics**: `stdout_excerpt`, `stderr_excerpt` (≤800 chars, never
     used for scoring)
3. Size limit `MAX_STRUCTURED_RESULT_CHARS = 200_000`. Oversize → explicit
   `error: STRUCTURED_RESULT_TOO_LARGE`, `ok: False`, `answer_text: None`.
   Never truncate-and-continue.
4. Parent `(response, cost)` unpacked at the data layer; cost never enters
   `answer_text`.
5. `answer_sha256` provides full-response traceability.
6. JSON parse failure refuses scoring (`JSON_PARSE_FAILED`) — never falls
   back to scraping truncated logs for numbers.
7. Subprocess reads use UTF-8 (`errors="replace"`), fixing Windows GBK
   decode crashes on Unicode responses.

## New behaviour vs old

| | old | new |
|---|---|---|
| stdout | `[-800:]` truncated | full parse; diagnostics excerpted |
| scoring source | possibly truncated log | `answer_text` structured field |
| tuple | cost in same string | `answer_text` / `cost_meta` split |
| oversize | silent truncation | explicit failure |
| parse failure | log scraping | refuse scoring |

## Regression tests (10 in test_r23_output_complete.py + 5 in test_r22)

- 600 / 2000 / 8000-char responses not truncated
- Unicode, newlines, backslashes, LaTeX, `\boxed{42}` preserved
- tuple vs plain output separated
- oversize fails explicitly
- diagnostics excerpted while answer complete
- JSON parse failure refuses scoring
- old-implementation truncation caught (`answer_len > 800`)
- `answer_sha256` matches content
