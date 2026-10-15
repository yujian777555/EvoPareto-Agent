# Phase5-R3-R1 — Genome Behavior Audit

**RQ1:** Does Agent Genome change execution behavior beyond prompt text?

## Before (R3)

`AgentBuilder._run_with_llm` embeds genome strings into the prompt;
`_mock_run` multiplies capability tables. No memory store, reflection loop,
tool allowlist, or hard budget.

## After (R3-R1)

`src/runtime/behavioral_agent.py` — `BehavioralAgent`:

| genome field | behavioral mechanism | tests |
|--------------|----------------------|-------|
| `planner_strategy` | step graph (`direct` vs `tree_search` vs `plan_and_solve`…) | `test_planner_changes_step_structure` |
| `memory_strategy` | `MemoryStore` read/write; `none` ⇒ zero reads | `test_memory_none_no_reads`, `test_memory_episodic_reads_after_run` |
| `reflection_strategy` | reflection event + retry when not successful | `test_reflection_emits_events_when_enabled` |
| `tool_policy` | `ALLOW_TOOLS` allowlist; denied tools not executed | `test_no_tools_blocks_required_tool` |
| `reasoning_budget` | `BudgetMeter` max steps/tokens | `test_budget_limits_steps` |

## PROMPT_ONLY labels

| field | status |
|-------|--------|
| planner_strategy | **BEHAVIORAL** (step structure) |
| memory_strategy | **BEHAVIORAL** (MemoryStore gates) |
| reflection_strategy | **BEHAVIORAL** (retry/refine path) |
| tool_policy | **BEHAVIORAL** (allowlist enforcement) |
| reasoning_budget | **BEHAVIORAL** (BudgetMeter) |

Note: LLM **text quality** scoring in `*_real.py` adapters remains a separate
PROXY layer (`evaluation_kind=real_llm_proxy`) — not genome behavior.

## Residual risk

BehavioralAgent is a local policy scaffold for consistency tests. When native
ALFWorld is available, these same gates should wrap the real env loop.
