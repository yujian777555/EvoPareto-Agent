# Token & Cost Hard Caps (Task 2)

**Gate B: PASS**

## Pricing

`estimate_cost(..., peak=True)` by default — **peak cache-miss** rates
($0.30/1M in, $1.20/1M out). Cache-hit discounts are never a safety
premise. Unknown model → `UnknownModelPrice` → fail-closed.

## Pre-send sequence (enforced in code)

```
VALIDATE REQUEST (conservative input-token upper bound)
  -> VALIDATE MODEL / PRICE (worst_case_cost)
  -> CHECK INPUT TOKEN BOUND (per-request 2000)
  -> RESERVE REQUEST SLOT (<=300 physical)
  -> RESERVE INPUT/OUTPUT TOKEN BUDGET (cumulative caps, atomic)
  -> RESERVE WORST-CASE COST (2000*0.30/1M + 500*1.20/1M)
  -> SEND HTTP
  -> RECONCILE TRUSTED USAGE (usage must be present and within caps)
  -> COMMIT LEDGER
```

Reservation is the **conservative maximum** for the token bounds, not a flat
low fee.

## Hard limits (code-enforced)

| Limit | Value | Enforced where |
|---|---:|---|
| input tokens / request | 2000 | `InputTokenCapExceeded` before send |
| output tokens / request | 500 | sent as `max_tokens`; cap must be >0 |
| cumulative input tokens | 2 000 000 | BudgetDB atomic check+reserve |
| cumulative output tokens | 200 000 | BudgetDB atomic check+reserve |
| physical requests | 300 | `BudgetExceeded` before send |
| total cost | $5.00 | `BudgetExceeded` on reservation |

Token quotas are reserved at `acquire_ticket` and **not** double-counted at
settle. Concurrent callers cannot overshoot (single `BEGIN IMMEDIATE`).
Restart keeps `physical_attempts`, `tokens_*`, `spent_cost` and the billing
block.

## Uncertain billing

HTTP_TIMEOUT, HTTP_429/500, CONNECTION_RESET, MISSING_USAGE, PARTIAL_RESPONSE
after a physical send all call `settle_unknown_and_block()` in one transaction
— never `$0` settle-and-continue. Evidence is preserved in `request_ledger`
(`request_status=fail_closed`, `error_kind` set).

## Observation for Planner

AFlow's optimizer prompt measured ~6049 conservative input tokens, which
**exceeds** the frozen 2000/request cap and was correctly blocked. Per
protocol this is reported, not silently widened. The real pilot needs either a
higher `MAX_INPUT_TOKENS_PER_REQUEST` or a smaller optimizer prompt.
