# Phase5-R3-R2 — Final Report

## 1. Git

| item | value |
|------|-------|
| HEAD | this commit |
| origin/main | pushed |
| working tree | clean after commit |

## 2. DeepSeek `deepseek-flash`

**Available** (host + Docker). `thinking.type=disabled` now unified in backend.

## 3. TextWorld install

**YES** — Docker `alfworld-local:tw`, **4027** native games, volume `alfworld-data`.

## 4. Official `env.reset()` / `env.step()`

**YES** — `AlfredTWEnv.init_env` → `TextworldBatchGymEnv.reset/step`.
Observation, `admissible_commands`, `won`, `score` all native.

## 5. BehavioralAgent in pipeline

**YES** — `InteractiveAgent` wraps memory/reflection/tool/budget and is used
by `native_llm_pilot.py` against native env + DeepSeek.

## 6. Genome dimensions

| dim | effect |
|-----|--------|
| planner | plan prefixes / step structure |
| memory | MemoryStore read/write → prompt history |
| reflection | second-pass LLM on parse failure |
| tool_policy | allowlist (env is text; tools limited) |
| reasoning_budget | BudgetMeter steps/tokens |

## 7. Success source

Native pilot success from **`won`** only. Capability prior not used.

## 8. Episodes

| run | n | success | eval_kind |
|-----|---|---------|-----------|
| rule policy | 3 | 0 | real_environment |
| DeepSeek pilot | 2 | 0 | real_environment |

Failures allowed; chain correctness is the gate.

## 9. API / tokens / cost

DeepSeek pilot: **8–10 calls/episode**, tokens recorded in
`results/native_alfworld/pilot/deepseek_ep2.json`. No mock fallback.

## 10. Train/test independence

Official splits; pilot on `valid_unseen`. Schema fail-closed tests pass.

## 11. Tests

`pytest` **all green** (host). Native tests run in Docker scripts.

## 12. Remaining blockers

1. Evolutionary loop not yet executed over native env at scale.
2. True Random-Search baseline module missing.
3. Paper real-env tables await Planner-approved budget.

## Final status: `ACCEPTED_NATIVE_PILOT`

(Native env + LLM closed loop works; small pilot only; no fake results.)
