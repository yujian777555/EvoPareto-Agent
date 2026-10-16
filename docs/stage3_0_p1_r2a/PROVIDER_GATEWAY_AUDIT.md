# Provider Gateway Audit

| Check | Result |
|---|---|
| concurrent reservations | True |
| budget exhausted enforced | True (BudgetExceeded) |
| restart keeps ledger | False |
| unknown cost fail-closed | True |
| blocked allows send | False |
| optimizer LLM intercepted | True |
| workflow LLM intercepted | True |

`AFlow AsyncOpenAI default base_url must be overridden to gateway at pilot time` — at pilot, ALL LLM traffic must route
through the gateway; default AsyncOpenAI endpoint must be overridden.
Billing record fields: run_id / provider / model / logical+physical request ids
/ reserved_cost / reported_tokens / observed_cost / cumulative / status
(implemented in BudgetDB tickets + meta).
