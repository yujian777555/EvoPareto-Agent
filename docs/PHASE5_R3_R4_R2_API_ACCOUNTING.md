# Phase5-R3-R4-R2 — API Accounting

## Fixes

1. **Structured LLM returns** (`{text, usage, model}`) parsed by
   `parse_llm_return` — episode keeps real tokens/cost.
2. **Global APICallGate** shared across horizons/episodes (not per-run).
3. **402 fail-fast** (`BLOCKED_BILLING`), 401/403 `BLOCKED_AUTH` — no retry ladder.
4. Failed physical requests still settle into the ledger.
5. Estimated vs actual tokens separated.

## D2 snapshot (deepseek-flash)

| metric | value |
|--------|-------|
| physical requests ok | 34 |
| failed | 0 |
| actual tokens | 12,239 in + 224 out |
| estimated reserve tokens | 9,670 |
| cost | $0.00127 |
| max_calls / max_cost | 80 / $1.00 |

Episode-level usage now non-zero (see success provenance JSON).

## Tests

`tests/test_r4r2_integrity.py`: global shared budget, 402 fail-fast,
usage propagation, trajectory fields.
