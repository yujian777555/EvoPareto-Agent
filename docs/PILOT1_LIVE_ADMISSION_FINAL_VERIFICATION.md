# Pilot 1 Live Admission Final Verification

**Status:** `ACCEPTED_PILOT1_LIVE_ADMISSION`  
**Real DeepSeek API calls:** **0**  
**Git at evidence time:** `f0db3af37eb2326fb273b8378302d30d8466dac5` (= origin/main before this commit)

Research direction unchanged: NSGA-III · PEEM · PPEC · Agent Genome ·
`candidate_2obj` (`performance↑`, `cost↓`).

---

## 1. Acceptance table

| Check | Requirement | Result | Evidence |
|---|---|---|---|
| Live Manifest Lock | actually wired | **PASS** | `live_manifest_mock.json`, `test_live_entry_mock_backend_uses_manifest_lock` |
| Forced Game Reset | correct game every reset | **PASS** | `test_episode_runner_second_reset_keeps_same_game` |
| Actual Game ID | equals manifest | **PASS** | `native_smoke.json` `manifest_game_match=true` |
| Identity before first LLM | verified | **PASS** | `test_identity_error_sends_zero_http` (mismatch → 0 LLM) |
| Unknown-cost settle | one atomic txn | **PASS** | `atomic_billing_block.json` |
| Billing Block | persistent | **PASS** | `test_billing_block_survives_restart` |
| Concurrent race | no ticket after block | **PASS** | `test_concurrent_interleave_no_ticket_after_block_commit` · `test_two_process_cannot_bypass_block` |
| Mock HTTP E2E | real chain | **PASS** | `http_e2e_reconciliation.json` |
| Backend/Ledger/Episode | reconciled | **PASS** | tokens 100/20 · cost `$1.4e-5` all three equal |
| Native ALFWorld | reset/step | **PASS** | `native_smoke.json` `native_dry_run_status=PASS` |
| Real API calls | 0 | **PASS** | mock server only |
| Git | clean, tests green | **PASS** | `python -m pytest -q` all green |

## 2. Native Docker smoke

Command:

```bash
docker run --rm -v alfworld-data:/data \
  -v <repo>/src:/src -v <repo>/scripts:/scripts -v <repo>/results:/results \
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ \
  alfworld-local:tw python /scripts/native_offline_smoke.py
```

Result (`results/pilot1_live_admission_verified/native_smoke.json`):

```
manifest_sha256: 27b54ac0b65133d1d95c7c06b27873581bf6a4ac84f56f7dc936e6c97ddb13b7
selected_manifest_game_id:
  /data/json_2.1.1/valid_train/look_at_obj_in_light-Book-None-DeskLamp-302/trial_T20190909_085137_911990
actual_game_id: …/trial_T20190909_085137_911990/game.tw-pddl
canonical_game_id: …/trial_T20190909_085137_911990
checks: manifest_game_match · native_reset_pass · native_step_pass
        episode_runner_pass · fitness_2d_pass  → all true
native_dry_run_status: PASS
```

`won=false` (Mock LLM, honest) · fitness `[0.0, 0.0]` valid under
`candidate_2obj` · `evaluation_kind=real_environment`.

## 3. Live entry + mock backend (same lock as smoke)

`test_live_entry_mock_backend_uses_manifest_lock` runs `live_run()` with a
patched native env + MockLLMBackend, asserting the identical
`resolve_locked_live_task` + `make_locked_reset` path:

- `manifest_sha256` matches the frozen manifest
- `selected_manifest_game_id` = manifest task 0
- `canonical_game_id` matches after `force_game_file` reset
- `git_sha` written into the episode log
- 0 real API calls

Recorded in `results/pilot1_live_admission_verified/live_manifest_mock.json`.

## 4. Atomic billing block

| Scenario | Test | Outcome |
|---|---|---|
| normal settle | `test_normal_request_full_settle` | 1 attempt, ledger=backend, not blocked |
| unknown usage | `test_unknown_usage_atomic_block` | block `UNKNOWN_USAGE:missing usage fields`, 2nd send = 0 |
| unknown rate | `test_unknown_rate_atomic_block` | block `UNKNOWN_RATE` |
| restart | `test_billing_block_survives_restart` | block survives new BudgetDB |
| two processes | `test_two_process_cannot_bypass_block` | 0 tickets / 10 blocked |
| interleave race | `test_concurrent_interleave_no_ticket_after_block_commit` | after commit: 5 acquires, 0 success |
| txn failure | `test_transaction_failure_aborts_and_no_false_settle` | no false settle, original ticket intact |
| double settle | `test_same_ticket_not_double_settled` | physical_attempts stays 1 |
| retry bypass | `test_retry_cannot_bypass_billing_blocked` | BillingBlocked, hits stay 1 |
| prior ledger | `test_prior_successful_ledger_not_broken` | settled_ok + spent_cost preserved |

## 5. HTTP → Backend → Episode → SQLite

`results/pilot1_live_admission_verified/http_e2e_reconciliation.json`:

```
http_hits=1 · logical_llm_calls=1 · physical_attempts=1 · settled_ok=1
tokens_in  100 == ledger == backend == episode
tokens_out  20 == ledger == backend == episode
cost  $1.4e-5 == ledger == backend == episode
      == frozen deepseek-flash-2026-v1 rate formula
real_deepseek_calls = 0
```

Failure paths (local mock server request counters):

- 200 + empty completion → block + no second send
- 401 / 402 / 429 → physical attempt recorded + block (missing usage)
- timeout → attempt recorded, no hanging ticket
- missing usage → **atomic block → second network send count = 0**
- unknown model (`gpt-99`) → `UNKNOWN_RATE` block

## 6. Commands executed

```bash
python -m pytest -q
python -m pytest tests/test_pilot1_final_patch.py \
                 tests/test_pilot1_microfix.py \
                 tests/test_pilot1_final_admission.py -q   # 35 passed
git diff --check
docker run --rm … alfworld-local:tw python /scripts/native_offline_smoke.py
```

## 7. Answers to the six acceptance questions

1. **Live entry uses forced manifest lock?**  
   YES — `resolve_locked_live_task` + `make_locked_reset` in
   `scripts/pilot1_entry.py`; proven by
   `test_live_entry_mock_backend_uses_manifest_lock`.

2. **EpisodeRunner reset keeps the same game identity?**  
   YES — EpisodeRunner receives `locked_reset`, which forces
   `force_game_file` and re-verifies canonical ID on **every** reset
   (`test_episode_runner_second_reset_keeps_same_game`).

3. **Unknown-cost settle and billing block one atomic transaction?**  
   YES — `BudgetDB.settle_unknown_and_block` in a single `BEGIN IMMEDIATE`
   (`test_unknown_usage_atomic_block`, `atomic_billing_block.json`).

4. **Concurrency and restart cannot bypass the block?**  
   YES — check inside `BEGIN IMMEDIATE`; two-process and interleave tests
   pass; block survives SQLite reopen.

5. **Mock HTTP → Backend → EpisodeRunner → SQLite real reconciliation?**  
   YES — `http_e2e_reconciliation.json`: tokens and cost equal across all
   three layers, 1 physical hit, frozen rates.

6. **May we approve real DeepSeek + ALFWorld Pilot 1?**  
   **YES — all admission gates PASS.** Recommend Planner approve live Pilot 1
   under the frozen caps: **≤120 physical HTTP · ≤$0.05 estimated cost**,
   `deepseek-flash`, `valid_train`, H=30, `candidate_2obj`, `task_index=0`.

---

Raw evidence directory: `results/pilot1_live_admission_verified/`  
(`native_smoke.json`, `live_manifest_mock.json`, `http_e2e_reconciliation.json`,
`atomic_billing_block.json`, `test_summary.json`, `task_identity.json`).
