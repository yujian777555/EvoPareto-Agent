# Provider Gateway End-to-End Integration (Task 2)

**Evidence class:** MOCK_TEST (Mock HTTP provider, 0 real LLM)
**Module:** `src/runtime/provider_gateway.py`
**Tests:** `tests/baseline_first/test_provider_gateway_e2e.py` (16 tests)

## Requirement: real chain, not static scan

Previous R2A marked `optimizer_llm_intercepted=True` from a code scan. That is
not end-to-end proof. This stage actually runs both call chains against a local
OpenAI-compatible Mock HTTP provider.

## Chains exercised

```
AFlow Optimizer  -> GatewayLLM.__call__ -> PhysicalBudgetGate -> HTTP POST /v1/chat/completions
AFlow Workflow   -> Operator.llm        -> PhysicalBudgetGate -> HTTP POST /v1/chat/completions
```

| Check | Result |
|---|---|
| Optimizer path performs real HTTP | PASS (provider.requests_seen == 1) |
| Workflow/Operator path performs real HTTP | PASS (call_with_format + __call__) |
| Both share one choke point (install_aflow_gateway) | PASS |
| Budget reserved BEFORE socket send | PASS (cap test shows 0 HTTP after exhaustion) |
| No bypass | PASS (urllib only inside GatewayLLM._http_chat) |

## Per-request ledger (not meta overwrite)

`RequestLedger` table `request_ledger` — **append-only**, one row per physical
request with: run_id, provider, model, logical_request_id, physical_request_id,
ticket_id, max_input_tokens, max_output_tokens, reserved_cost,
reported_tokens_in/out, observed_cost, cumulative_cost, request_status,
error_kind, http_status.

History is never replaced by a single meta key. `test_request_ledger_is_append_only`
verifies distinct physical ids and ticket ids per row.

## Budget hard limit

| Scenario | Result |
|---|---|
| hard cap reached -> further requests rejected | PASS (BudgetExceeded before HTTP) |
| concurrent 8x4 requests cannot break cap | PASS |
| restart keeps cumulative spend + ledger rows | PASS |

## Fail-closed (all tested)

| Failure | Behaviour |
|---|---|
| MISSING_USAGE | settle failed + billing_blocked + record fail_closed |
| UNKNOWN_MODEL_PRICE | UnknownModelPrice + billing_blocked |
| TIMEOUT | record failed, exception propagates |
| PARTIAL_RESPONSE | settle failed + billing_blocked |
| HTTP_500 / HTTP_429 | record failed |

## Generated Workflow isolation (items 7-8)

`run_workflow_code_isolated` runs generated `Workflow` code in Docker:

```
docker run --rm --network none --memory 256m --pids-limit 64
  (no host env secrets, no docker.sock, no system proxy)
```

Negative test: a Workflow that tries to read `R2A_HOST_SECRET` and open a socket
to 1.1.1.1 returns `{'secret': None, 'net': 'OSError'}` — secrets invisible,
network denied. Code cannot reach the model except through the controlled
GatewayLLM interface.

## Verdict

**OPTIMIZER_GATEWAY_E2E: PASS**
**WORKFLOW_GATEWAY_E2E: PASS**
**REQUEST_LEVEL_LEDGER: PASS**
**BUDGET_FAIL_CLOSED: PASS**
**SANDBOX_E2E: PASS**
**NO_UNAUTHORIZED_EGRESS: PASS**
