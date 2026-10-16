# Stage 1.7-R1 Genome Compatibility

| Gene | Still real? | Notes |
|---|---|---|
| memory_strategy | **yes** | history window k=0/1/3 enforced in shared prompts |
| reasoning_budget | **yes** | BudgetMeter max steps/tokens |
| reflection_strategy | degenerate | none vs parse-fail retry |
| tool_policy | NO-OP (native) | unchanged |
| planner_strategy | **PROMPT_ONLY** | shared SubgoalPlanner ≠ 5 planners; tree_search still UNIMPLEMENTED |

`grounded_planner_v1` provides **shared** structure; LLM chooses the action.
Different genomes still differ in memory window and budget. If future paired
runs collapse to identical trajectories, treat as `GENOME_EXECUTION_DEGENERATE`
risk before PEEM/PPEC claims.

No Genome encoding expansion this round.
