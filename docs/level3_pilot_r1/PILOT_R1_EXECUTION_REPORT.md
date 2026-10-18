# Level 3-Pilot-R1 Execution Report — Full Real Loop

**Run id:** `pilot-0fe2d163df`
**Authorization:** REUSED_PERSISTENT (`~/.evopareto/state/`, shared cumulative $5)

## P0 — authorization moved outside Git

- persistent path: `~/.evopareto/state/level3_pilot_authorization.json`
- git-tracked copy removed from version control and gitignored
- missing/corrupt record -> fail-closed (no auto-create)
- historical consumption preserved: 2 requests / $0.0008979 / 151 in / 640 out
- tests prove delete / git-rollback / run-id / DB-path cannot restore quota

## Phase-specific output caps

| Phase | max_tokens |
|---|---:|
| pilot_math | 500 |
| pilot_optimizer | **1800** |
| pilot_workflow_ipc | 500 |

Reservation, request `max_tokens` and worst-case cost share the same phase cap.

## Real execution — complete loop

| Metric | Value |
|---|---|
| REAL_HTTP_REQUESTS (cumulative) | **7** / 300 |
| REAL_INPUT_TOKENS (cumulative) | 469 |
| REAL_OUTPUT_TOKENS (cumulative) | 1368 |
| BUDGET_DEBITED_USD | **0.0018669** |
| USAGE_COST_ESTIMATE_USD | 0.000969 |
| PROVIDER_INVOICE_COST_USD | NOT_VERIFIED |
| BUDGET_REMAINING_USD | 4.9981331 |
| STOP_REASON | **PILOT_MINIMAL_SLICE_COMPLETE** |

### Stage 1 — GSM8K train math
- predicted `10` = gold `10` — **CORRECT**

### Stage 2 — Real Optimizer XML (1800 tokens)
- XML complete: **True** · finish_reason: stop
- graph compiles: **OK** · has Workflow: True
- modification: Split into solve-then-verify passes with self-consistency check to catch arithmetic errors.
- real generated graph uses **self-consistency voting** (3 drafts + verify pass)

### Stage 3 — Candidate Bundle
- graph_sha: `a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b`
- prompt_module_sha: `6b773b969598060e32c18f409d2277f4707f9e67152b25357aa111e855f41579`
- bundle_sha: `035b51cb257718d8d300ce4793984f8c115ca9efb443f433d01195c94cace173`
- prompt_contract: SERIALISED_INSTRUCTION_REPR

### Stage 4-6 — Docker → DeepSeek IPC → Host scoring
- docker_ok: **True** · returncode: 0
- IPC processed: **3** real DeepSeek calls
- predicted: `72` · gold (host only): `72`
- **TASK_CORRECT: True**

## Parent-child comparison

Both the initial math task (Stage 1) and the real generated candidate
(Stage 4-6) answered their GSM8K train tasks correctly. This is **two correct
task outputs** — NOT evidence of recursive self-improvement.

## Cost reporting (three-way)

| Column | Meaning | Value |
|---|---|---|
| budget_debited_usd | conservative charge to the authorization | 0.0018669 |
| usage_cost_estimate_usd | provider usage x configured prices | 0.000969 |
| provider_invoice_cost_usd | provider final bill | **NOT_VERIFIED** |
