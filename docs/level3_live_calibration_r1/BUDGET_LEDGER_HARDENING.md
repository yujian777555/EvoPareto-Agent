# Budget Ledger Hardening (Task B)

## Actual vs Reserved vs Unknown

| Kind | Meaning |
|---|---|
| ACTUAL | provider `usage` fields after settle |
| RESERVED | pre-send conservative quota (est_in + max_output) |
| UNKNOWN | post-send unverifiable → fail-closed block |

## Historical correction (live Level 3 run)

| Field | Previous report | Corrected |
|---|---:|---:|
| input tokens | 651 (RESERVED mislabelled) | **162** |
| output tokens | 1000 (RESERVED mislabelled) | **454** |

Per-request actuals: 57+105 = 162 in, 121+333 = 454 out.

Cost is a **usage-based ESTIMATE** at peak cache-miss rates —
not a provider final invoice.

## Persistent authorization identity

```
auth_id = level3-live-authorization-v1-f579a48a1e5b79ca
```

Budget caps bind to this identity, **not** a random Run ID. Deleting the budget
DB or rotating run ids does not restore consumed quota. Untrusted/unrecoverable
ledgers fail-closed.

## Safety gates preserved

Conservative reservation + atomic `BEGIN IMMEDIATE` unchanged. The fix only
corrects reporting; it does not weaken pre-send reservation, token quotas, or
fail-closed unknown-billing.
