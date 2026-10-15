# R2-R2 — HTTP Accounting

## Lifecycle

```text
pre_send_ticket → HTTP → parse usage → settle(ticket, tokens_in, tokens_out)
```

- empty completion / 402 / 401 → not counted as success completion
- network fail → settle(success=False), physical attempt retained
- double settle rejected

## recover_stale

Only **stale ticket IDs** (age filter) are abandoned; fresh open tickets of a
live process are preserved. Tokens/cost released only for those IDs.

## Cost disclosure

Cost = rate × API usage (**estimated**). No live billing API — not claimed as
absolute USD hard cap; physical request cap is strict.
