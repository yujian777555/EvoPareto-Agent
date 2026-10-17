# Structured Output Validation (Task 3)

**Gate C: PASS**

## Removed

The old fallback

```python
return {"modification": "gateway-mod", "graph": raw, "prompt": "INSTRUCTION = 'gw'"}
```

is **deleted**. Synthesising a valid-looking mutation from an invalid model
response would pollute the evolutionary record.

## New behaviour (`GatewayLLM.call_with_format`)

AFlow-compatible tags: `<modification>`, `<graph>`, `<prompt>`.

| Condition | Result |
|---|---|
| valid tags + `class Workflow` + compile OK | ACCEPTED |
| formatter validation failure | `StructuredOutputError` |
| missing modification / graph / prompt | REJECTED (`MISSING_*`) |
| incomplete XML/JSON | REJECTED |
| invalid Python | REJECTED (`INVALID_PYTHON`) |
| no `class Workflow` | REJECTED |

There is **no** synthetic success path. Invalid candidates are discarded (or
retried under budget); they never become fake successes.

## Retry policy

Format-repair retries must be explicitly budgeted (each costs a physical
request), preserve the original failed response in the ledger, and after the
retry limit the candidate is marked invalid. No silent prompt/graph mutation.
