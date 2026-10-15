# Phase5-R3-R4-R2 — Final Report

## 1. Git

| item | value |
|------|-------|
| Commit | this SHA |
| origin/main | pushed |
| working tree | clean |

## 2–3. Split verification (Docker, official data)

| split | train_eval | games in correct folder |
|-------|------------|-------------------------|
| valid_train | train | ✅ |
| valid_seen | eval_in_distribution | ✅ |
| valid_unseen | eval_out_of_distribution | ✅ |

Manifest overlap check available; frozen test not used for tuning.

## 4. Historical H=30 success

**`HISTORICAL_SUCCESS_UNREPLAYABLE`** (no action sequence in old JSON).

## 5. New positive control / success

**YES** — D2 ep0 on `valid_train` `won=True` in 3 steps; replay `match_won=True`.

## 6–7. New DeepSeek H=30 episodes

2 episodes, full trajectories; **1 success**, 1 env_done@30.  
Files: `results/native_alfworld/r4r2_pilot/d2_h30_valid_train.json`,
`success_replay/episode0.json`.

## 8. Real HTTP / tokens / cost

34 requests ok · 12,463 actual tokens · **$0.00127** · global gate 80/$1.

## 9. 402 / retry / budget tests

402 fail-fast implemented + tested; concurrent budget tests green.

## 10. Tests

Host pytest **all green** (incl. split integrity, traces, usage, 402).  
Docker: split_check + D2 + replay.

## 11. Four-method pilot ready?

**YES (protocol)** on valid_train @H=30 with shared native evaluator +
APICallGate; awaiting Planner budget approval. Not run this phase.

## 12. Objectives still unfit for main tables

efficiency · robustness · autonomy (see objective audit).

## 13. Final status

**`ACCEPTED_PROTOCOL_READY`**
