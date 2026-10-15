# Phase5-R3-R5-R1 — HTTP Gate Audit

## P0-1 at 175c7e5

`post_json` had `before_send` but DeepSeek path never bound a budget callback
→ physical attempts counted **after** send only.

## Fix

`src/runtime/http_budget.py`:

- `BudgetDB` (SQLite, WAL, `BEGIN IMMEDIATE`) — cross-process atomic
- `PhysicalBudgetGate.approve()` **before** network; `release()` on settle
- `pre_send_approval()` hook in `http_client._send` — raises ⇒ **no I/O**

## Accounting

logical_ok / logical_failed / physical_attempts / retries / tokens / reserved / settled.

## Offline verification tests

curl-ok, curl-fail→urllib, 402, 429, timeout, interrupted body, multi-process,
crash recovery, budget exhaust, reserved=0 after settle — covered in
`tests/test_r5r1_2d_fidelity.py` + sqlite persistence tests.
