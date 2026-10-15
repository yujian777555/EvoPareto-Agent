# Phase5-R3-R3 — Final Report

## 1. Git

| item | value |
|------|-------|
| HEAD | this commit |
| origin/main | pushed |
| working tree | clean |

## 2. Native Environment

| item | value |
|------|-------|
| Docker | `alfworld-local:tw` + volume `alfworld-data` |
| versions | alfworld 0.4.2 / textworld 1.7.0 |
| reset/step/won | **verified** |
| game IDs | **rotated** via `episode_index` (2 unique in micro pilot) |
| splits | valid_train / valid_seen / **valid_unseen** (held-out) |

## 3. InteractiveAgent

| property | status |
|----------|--------|
| episode isolation | **YES** (fresh Memory/Budget/reflection) |
| goal persistence | **YES** (from env “Your task is to: …”) |
| memory in decisions | YES (history in prompt) |
| reflection | YES (second decision on parse fail) |
| tool_policy | **INACTIVE_IN_NATIVE_ENV** |
| budget | REAL stop on exhaust (no look-loop) |

## 4. Native Evolution

| arm | native evaluator? |
|-----|-------------------|
| Random Search | YES (`RandomSearchSampler`) |
| NSGA-III | YES (`MemoryEvolutionLoop` + `NativeEvolutionEvaluator`) |
| NSGA-III+PEEM | YES |
| NSGA-III+PEEM+PPEC | wired (same evaluator) |

FakeLLM Docker smoke: `SMOKE_OK`, evolution HV computed, RS independent.

## 5. Objective

| obj | source | prior? |
|-----|--------|--------|
| performance | env won | no |
| efficiency | steps + tokens | no |
| cost | API usage $ | no |
| robustness | stall-aware | partial |
| autonomy | behavioral proxy | reduced (no config-name prior) |

**See `PHASE5_R3_R3_NATIVE_OBJECTIVE_AUDIT.md` — not all five approved for main tables.**

## 6. DeepSeek micro pilot

| item | value |
|------|-------|
| model | `deepseek-flash` |
| API calls | **57** (cap 100) |
| tokens in/out | 23,102 / 307 |
| cost | **$0.0024** (cap $1) |
| episodes | 16 |
| success | **0** |
| terminations | 2× max_steps, 14× budget_exhausted |

Goals present; game rotation works. **0% success on OOD tasks in ≤5 steps** —
honest failure, env `won` unchanged.

## 7. Tests

- Host pytest: **all green** (incl. episode isolation, budget stop, parse reflection, RS independence)
- Docker native: `SMOKE_OK` + micro pilot JSON
- DeepSeek: within hard caps

## 8. Research value

| question | answer |
|----------|--------|
| native evolution loop runs? | **YES** (FakeLLM + DeepSeek) |
| NSGA-III native fitness? | YES |
| method differences on native? | **not yet** (0 success ⇒ weak signal) |
| multi-seed ready? | **Not yet** — need longer horizons / easier train split / objective approval |
| evidence supports | engineering validity of loop |
| evidence does **not** support | PEEM/PPEC superiority claims on ALFWorld |

## 9. Final status

**`ACCEPTED_INTEGRATION_ONLY`**

Native evolution loop is real and auditable; performance claims remain blocked
by 0-success micro scale + incomplete objective validation.
