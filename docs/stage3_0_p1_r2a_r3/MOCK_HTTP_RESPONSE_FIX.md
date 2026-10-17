# Mock HTTP Response Fix (Task B)

## Problem

`GoldBlindGatewayLLM._http_chat()` posted to the provider then **discarded the
response** and returned locally constructed content. That is not evidence that
the provider body is parsed, validated and billed.

## Fix

`MockHTTPProvider` now returns deterministic gold-blind bodies
(`mock_chat_completion_body`) based on the request prompt:

| request kind | provider returns |
|---|---|
| `Solve: / Task:` | `The final answer is #### <first number in question>` |
| optimizer / GraphOptimize | valid `<modification>/<graph>/<prompt>` XML |

`GatewayLLM` uses the **provider** body unchanged. `HTTP_RESPONSE_OVERRIDDEN = False`.

## Failure-mode matrix (tested)

| scenario | behaviour |
|---|---|
| HTTP_200_VALID | accepted, billed |
| HTTP_200_INVALID_JSON | rejected, ledger `failed` |
| HTTP_200_MISSING_USAGE | fail-closed + billing_blocked |
| HTTP_200_MALFORMED_XML | `StructuredOutputError` |
| HTTP_429 | rejected, ledger recorded |
| HTTP_500 | fail-closed + billing_blocked |
| HTTP_TIMEOUT | fail-closed + billing_blocked |
| EMPTY_RESPONSE | rejected |

No silent exception swallowing; no fabricated content advances the search.

## Ledger reconciliation

Every HTTP POST has a ledger row with logical/physical request id, model,
usage tokens, reserved/observed cost, status. `test_ledger_reconciles_with_http`
asserts `len(rows) == len(provider.requests_seen)`.
