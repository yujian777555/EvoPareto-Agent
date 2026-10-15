# Phase5-R3-R2 — Runtime Wiring & API Protocol

## Runtime chain (now real)

```text
Genome → InteractiveAgent (memory/reflection/tool/budget)
      → DeepSeek deepseek-flash (thinking.type=disabled)
      → Native AlfredTWEnv.step(admissible_action)
      → won/score → success (real_environment)
```

## Fixes (Stage A)

| issue | fix |
|-------|-----|
| empty completion | backend sends `thinking.type=disabled`; empty content **raises** |
| budget only pre-check | `src/runtime/budget.py` thread-safe reserve/settle |
| memory write-only | `as_context()` feeds prompts; `none` ⇒ zero reads |
| reflection tag-only | retry pass with reflect event when first parse/outcome fails |
| API params mismatch | model `deepseek-flash` + thinking disabled in backend & diagnostics |

## Schema fail-closed

`src/evaluation/schema_guard.py` rejects:
- capability prior in `real_environment` episodes
- cross-benchmark task schema mix

## Stage E pilot (2 episodes, native + DeepSeek)

```text
evaluation_kind=real_environment
api_calls=8,10
success=0/2 (OOD tasks, 8-step budget — allowed to fail)
WROTE results/native_alfworld/pilot/deepseek_ep2.json
```

Acceptance of Stage E is **execution chain**, not success rate.

## Remaining gaps

1. Evolution loop not yet driven inside Docker native env at scale.
2. Random-Search arm not a separate module (selection still NSGA-III).
3. Large API budget not spent (by design until Planner approves).
