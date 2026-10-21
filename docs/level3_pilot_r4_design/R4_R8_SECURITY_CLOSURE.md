# R4-R8 Security Closure Report

**Baseline:** `31a9aba876fbe22f036a53b220bb21726e928e3f`  
**Real API:** **0** · Auth ledger read-only · PHASE2 / R3 / v1 confirm unchanged

## Task A — P0 authorization loop

| Control | Implementation |
|---|---|
| Ledger mandatory | `verify_execution_allowed_real(..., ledger=None)` → `BUDGET_LEDGER_REQUIRED` |
| Unforgeable real path | real entry **loads** controlled file + verifies `record_sha256` self-hash; caller `source='controlled_file'` objects unused |
| Strict numerics | `strict_number` rejects bool/str/NaN/inf; `20260601.0` / `True` rejected as seeds |
| Cumulative multi-R | scheme 1: sum demand over **all** `planned_r_values` (R=6+R=10) vs remaining |
| HTTP gate | `post_json_r4` always gates; **no gate installed → `R4_GATE_NOT_INSTALLED`** (socket 0) |
| Concurrency | synthetic `BudgetDB` reserve/settle fail-closed (`max_physical`) |

**All attack paths: HTTP physical send count = 0.**

## Task B — contamination audit

* Pinned exclusion contract (path + expected SHA + size + rule_id); **hash mismatch → rescan**.
* Fragment head/middle/tail matches are **hits**, never `NO_HIT`.
* Directory skips (`.git`/`external`/…) logged with impact statement.
* Suffixes extended: html/htm/rst/ipynb/cfg/ini/toml.
* `PHASE2_EVOLUTION_MEMORY.md` bytes unchanged → **`CONFIRMATION_INDEPENDENCE_BLOCKED`**.

## Task C/D — freeze + seeds

* v2 freeze: **no `execution_authorized`**; structure verify `''`; SHA recomputed.
* IUT-only F2; Holm(2) alternative text removed from active builder/docs.
* Seeds: fixed `BASE_SEED`; non-canonical keys (`06`) rejected; type attacks covered.

## Tests (R8 actual, JUnit)

| Suite | passed / failed / skipped |
|---|---|
| P0 security | 16 / 0 / 0 |
| Auth/budget | 37 / 0 / 0 |
| HTTP gate | 4 / 0 / 0 |
| Audit | 32 / 0 / 0 |
| Freeze/stats | 30 / 0 / 0 |
| IPC/historical | 64 / 0 / 0 |
| **Full (authoritative rerun)** | **1149 / 0 / 2** (1151) RETCODE 0 |

*Note:* one intermediate full run showed a transient flake (`test_l3r21_multiprocess` encoding); immediate rerun was clean. Counts above are from the successful rerun.

## Integrity

R3 0 modified · R3 gate unchanged · v1 `1771a67c…` · PHASE2 `abab3a36…` · auth `244 / $0.0363972` · no sim results in formal dirs.

## Status ladder

| Status | Value |
|---|---|
| `CODE_FIXED` | **YES** |
| `OFFLINE_TESTS_PASS` | **YES** |
| `PRODUCTION_ADAPTER_READY` | YES (Parent identity, mock model) |
| `R4_PIPELINE_READY` | **NO — NOT READY** |
| `REAL_MODEL_AUTHORIZED` | **NO** |
| Confirmation independence | **`CONFIRMATION_INDEPENDENCE_BLOCKED`** |
