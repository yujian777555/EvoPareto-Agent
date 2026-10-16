# Stage 1.7 Genome Phenotype Audit

Honest status of each gene (native path, after grounded planning).

| Gene | Levels | Execution effect | Label |
|---|---|---|---|
| planner_strategy | 5 | **not** 5 real planners; only prompt lines | PROMPT_ONLY / UNIMPLEMENTED(tree_search) |
| memory_strategy | 5 | history window k = 0 / 1 / 3 in shared prompts | EXECUTION_CONFIRMED |
| reflection_strategy | 5 | none vs retry-on-parse-fail only | EXECUTION_CONFIRMED (degenerate) |
| tool_policy | 5 | unused for ALFWorld admissible set | NO-OP (native) |
| reasoning_budget | int | max steps/tokens | EXECUTION_CONFIRMED |

## planner_strategy detail

| Name | Real plan? | Notes |
|---|---|---|
| direct | no | label only |
| cot | no | label only |
| plan_and_solve | no | one instruction sentence |
| tree_search | **UNIMPLEMENTED** | name ≠ tree search |
| reflexion | no | one instruction sentence |

`grounded_planner_v1` adds **shared** subgoal infrastructure; it is **not**
per-strategy. Future fair use: all evolutionary arms get the same runtime.

## Genome-difference risk (Gate D)

- Shared planner does not choose actions; LLM does.
- If Stage 1.8 shows near-identical trajectories across genomes, treat as
  **GENOME_PHENOTYPE_DEGENERATE** risk and revise before PEEM/PPEC claims.
- Do not advertise prompt labels as algorithmic planning.
