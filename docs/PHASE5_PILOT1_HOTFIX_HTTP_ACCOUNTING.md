# Pilot1 Hotfix — HTTP Accounting

## Cost settlement

`src/backend/rates.py` frozen table `deepseek-flash-2026-v1`.  
`_send` now: parse usage → `estimated_cost(model, tin, tout)` →
`settle_ticket(..., actual_cost=cost)`.

- usage missing → cost=0 + flagged unknown (not claimed real)
- backend/episode/SQLite reconcile via ticket id

## Status classes

| HTTP | completion | business success | physical |
|------|------------|------------------|----------|
| 200 + content | ok | yes | counted |
| 200 + empty | fail | **no** | counted |
| 401/402/403 | fail | no | counted, no retry |
| 429/5xx | fail | no | counted, bounded retry |
| timeout/conn | unknown | no | counted |

## Tests

`tests/test_pilot1_hotfix.py`: cost settle, cost budget block, empty-completion
≠ success, dry-run, live refuses without flag.
