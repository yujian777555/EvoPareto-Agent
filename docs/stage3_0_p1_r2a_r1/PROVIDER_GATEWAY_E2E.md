# Provider Gateway End-to-End (Task 3)

**Verdict: OPTIMIZER_GATEWAY_E2E = PASS · WORKFLOW_GATEWAY_E2E = PASS**

## Not a static scan

Earlier R2A set `optimizer_llm_intercepted = True` from a code read. This stage
runs **real HTTP** against a local Mock OpenAI-compatible provider.

```text
AFlow Optimizer  -> GatewayLLM -> PhysicalBudgetGate -> HTTP POST /v1/chat/completions
AFlow Workflow   -> Operator.llm -> GatewayLLM -> PhysicalBudgetGate -> HTTP POST ...
```

Evidence: `results/stage3_0_p1_r2a_r1/optimizer_gateway_e2e.json`,
`workflow_gateway_e2e.json` (pytest returncode 0 + provider.requests_seen).

## Per-request ledger (persistent, append-only)

`src/runtime/provider_gateway.py::RequestLedger` — table `request_ledger`, one
row per physical request:

```text
run_id · logical_request_id · physical_request_id · provider · model
input_tokens · output_tokens · reserved_cost · observed_cost · cumulative_cost
status · timestamp · error_kind · http_status · max_input/output_tokens · ticket_id
```

**No meta-key overwrite.** History is append-only and restart-persistent.

Evidence: `request_ledger_tests.json`.

## Fail-closed matrix (all tested, mock provider only)

| Scenario | Behaviour |
|---|---|
| HTTP_TIMEOUT | record failed, no free pass |
| HTTP_429 / HTTP_500 | record failed |
| MISSING_USAGE | settle failed + billing_blocked |
| UNKNOWN_PRICE | UnknownModelPrice + billing_blocked |
| PARTIAL_RESPONSE | settle failed + billing_blocked |
| BUDGET_EXHAUSTED | BudgetExceeded **before** socket send |
| CONCURRENT_REQUESTS | cap holds under 8x4 threads |
| PROCESS_CRASH / restart | cumulative spend + ledger rows survive |
| UNAUTHORIZED_PROVIDER_CALL | strict gate raises GateRequired |

All of these run against the local mock provider. **Zero DeepSeek calls.**
