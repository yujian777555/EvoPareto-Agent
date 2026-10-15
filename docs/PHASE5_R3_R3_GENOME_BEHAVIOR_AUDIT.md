# Phase5-R3-R3 — Genome Behavior Audit

| dimension | mechanism in R3-R3 | status |
|-----------|-------------------|--------|
| planner_strategy | prompt strategy line + plan prefixes (`plan_and_solve` / `tree_search` / `reflexion`); **not full tree search** | PARTIAL (prompt+structure) |
| memory_strategy | MemoryStore write then `as_context()` into prompt; `none` ⇒ empty history | BEHAVIORAL |
| memory semantic/hybrid | only different read window sizes | **LIMITED** (no semantic store) |
| reflection_strategy | failed parse → second LLM call with critique context; logged | BEHAVIORAL |
| tool_policy | `ALLOW_TOOLS` gates `invoke_tool`; **native TextWorld has no external tools** | **INACTIVE_IN_NATIVE_ENV** |
| reasoning_budget | BudgetMeter on LLM calls/tokens/steps; exhaust ⇒ episode stop | BEHAVIORAL |

## Notes

- `tool_policy` cannot be fully evaluated on ALFWorld TextWorld; treat as
  experimental limitation (supplementary offline tool tasks exist in mock suite).
- Budget uses **actual API usage deltas** in EpisodeRunner (not text-length only)
  when LLM reports usage; FakeLLM uses synthetic usage for offline tests.
