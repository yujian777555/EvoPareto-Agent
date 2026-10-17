# Atomic Budget Final Check (Task C)

Frozen pilot configuration applied to this offline admission run:

| Cap | Value |
|---|---:|
| MAX_INPUT_TOKENS_PER_REQUEST | **8000** |
| MAX_OUTPUT_TOKENS_PER_REQUEST | 500 |
| MAX_TOTAL_INPUT_TOKENS | 2,000,000 |
| MAX_TOTAL_OUTPUT_TOKENS | 200,000 |
| MAX_PHYSICAL_REQUESTS | 300 |
| MAX_COST_USD | **5.00** |

Pricing (peak cache-miss, re-check at pilot start):
input $0.30/1M, output $1.20/1M.

## Worst-case reservation

```
worst_case_per_request = 8000*0.30/1e6 + 500*1.20/1e6 = $0.003
300 requests          = $0.90  (< $5.00 hard cap)
```

Each request reserves `worst_case_cost(est_in, 500)` inside the same SQLite
`BEGIN IMMEDIATE` as the token quotas. The flat `est_cost_per_request` default
is not used when a real reserve is supplied.

## Verified

- reservation covers max allowed tokens
- input > 8000 rejected before send
- cumulative token quotas enforced
- concurrency cannot break the cap
- restart keeps consumption
- unknown billing fail-closed
- **no silent truncation** — an optimizer prompt over 8000 is reported, not clipped

## Optimizer prompt length (this run)

n = 4, max = 6049
(conservative bound `len+8`). Under the 8000 cap: **PASS**.
