# Pilot1 Hotfix — Final Report

## 1. Token/cost end-to-end settle?
**YES** — transport parses usage, computes frozen-rate cost, settles ticket
exactly once into SQLite.

## 2. 401/402 / empty completion / timeout classified?
**YES** — empty completion ≠ business success; billing/auth fail-fast; timeout
retains physical count with unknown usage.

## 3. SQLite cost reconciles with Backend/Episode?
**YES** — same ticket id; `spent_cost_usd` reflects `estimated_cost`.
Provider billed cost **not** claimed (no billing API).

## 4. Physical + cost budgets reliable?
**YES** — pre-send reserve; cost cap blocks; no restart refresh.

## 5. Real Pilot 1 ALFWorld+DeepSeek entry?
**YES** — `scripts/pilot1_entry.py` with `--live`, strict gate, native env.

## 6. Approve Pilot 1 ≤120 HTTP / ≤$0.05?
**YES — ready for Planner approval.** Not self-executed.

## Evidence

- dry_run.json (all checks true)
- tests/test_pilot1_hotfix.py + full pytest green
- rates.py frozen RATE_VERSION

## Status

**`ACCEPTED_PILOT1_READY`**
