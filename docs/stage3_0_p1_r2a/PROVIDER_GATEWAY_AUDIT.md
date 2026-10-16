# Provider Gateway & Budget Gate Audit (Task F)

**Evidence class:** DERIVED_STATISTICS (static path audit) + MOCK_TEST (budget ledger)
**verdict = BUDGET_GATE_PASS**

## F1 — request path audit

All model HTTP traffic in AFlow funnels through one choke point:

```
AFlow Optimizer ──► optimize_llm ──► AsyncLLM.__call__ ──► AsyncOpenAI.chat.completions
AFlow Workflow  ──► Operators.llm ──► AsyncLLM.__call__ ──► AsyncOpenAI.chat.completions
```

| Check | Result |
|---|---|
| AsyncLLM uses AsyncOpenAI | True |
| base_url configurable | True |
| optimizer via create_llm_instance | True |
| workflow via create_llm_instance | True |
| operators use injected llm | True |
| OpenAI client outside choke point | [] |
| unauthorized API paths | [] |
| data-download-only HTTP | ['data/download_data.py:import requests'] |

data/download_data.py fetches datasets from Google Drive; not a model API path. No chat/completions or OpenAI client outside scripts/async_llm.py.

**Interceptor:** at pilot time set `base_url` to the Provider Gateway **and** install
`PhysicalBudgetGate` around `AsyncLLM.__call__`. Both optimizer and workflow LLM are
then covered — there is no second model path.

## F2 — persistent billing fields

{
  "tickets_columns": [
    "id",
    "est_cost",
    "status",
    "created_at"
  ],
  "budget_columns": [
    "id",
    "max_physical",
    "max_cost_usd",
    "physical_attempts",
    "reserved_tickets",
    "settled_ok",
    "settled_failed",
    "reserved_cost",
    "spent_cost",
    "tokens_in",
    "tokens_out",
    "retries"
  ],
  "meta_keys_pre_write": [],
  "meta_keys_after_write": [
    "cumulative_cost",
    "logical_request_id",
    "max_input_tokens",
    "max_output_tokens",
    "model",
    "observed_cost",
    "physical_request_id",
    "provider",
    "reported_tokens",
    "request_status",
    "reserved_cost",
    "run_id"
  ],
  "required_fields": [
    "run_id",
    "provider",
    "model",
    "logical_request_id",
    "physical_request_id",
    "max_input_tokens",
    "max_output_tokens",
    "reserved_cost",
    "reported_tokens",
    "observed_cost",
    "cumulative_cost",
    "request_status"
  ],
  "all_required_present": true,
  "has_reserved_cost": true,
  "has_observed_cost": true,
  "has_cumulative": true,
  "has_token_counts": true,
  "ticket_status": "settled",
  "note": "F2 fields written to BudgetDB.meta by the pilot gateway wrapper"
}

Required fields written to `BudgetDB.meta` by the pilot wrapper:
run_id, provider, model, logical_request_id, physical_request_id,
max_input_tokens, max_output_tokens, reserved_cost, reported_tokens,
observed_cost, cumulative_cost, request_status.

## F3 — negative tests

| Test | Result |
|---|---|
| concurrent reservations | True (open_tickets=8) |
| budget exhausted enforced | True (['BudgetExceeded']) |
| unknown cost fail-closed | True (UNKNOWN_MODEL_PRICE) |
| blocked allows send | False |
| PROCESS_RESTART keeps ledger | True (attempts=2, spent=0.005) |
| billing block survives restart | True |

Fail-closed rule: unknown model price → `settle_unknown_and_block` → billing_blocked →
further `acquire_ticket` raises `BillingBlocked`. Restart does **not** reset consumption
and does **not** clear the block.

Generated code cannot use host credentials: pilot runs it in `--network none` with env
keys stripped (see SANDBOX_ACCEPTANCE.md).
