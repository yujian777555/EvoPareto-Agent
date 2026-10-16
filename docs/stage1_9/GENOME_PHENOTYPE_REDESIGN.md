# Genome Phenotype Redesign

## Current problems (evidence from Stages 1–1.8)

| Gene | Status |
|---|---|
| planner_strategy | PROMPT_ONLY (tree_search UNIMPLEMENTED) |
| memory_strategy | weakly real (window size) |
| reflection_strategy | degenerate 2-level |
| tool_policy | NO-OP on native path |
| reasoning_budget | real (steps/tokens only) |

Weak phenotypes ⇒ no Performance–Cost spread ⇒ evolution cannot work.

## Proposed executable genome (3–5 genes)

| Gene | Levels | Concrete execution effect | Cost impact |
|---|---|---|---|
| **planning_depth** | 0/1/2/3 | number of subgoal expansions before acting | tokens/latency ↑ with depth |
| **verification_policy** | none / single / retry_until_stable | re-observe & compare after action | extra calls |
| **context_budget** | 8 / 32 / 128 history tokens | prompt history window | input tokens |
| **action_selection** | greedy / topk_sample / beam2 | sampling among legal candidates | calls × beam |
| **cost_gate** | lenient / strict | per-call token cap & stop rule | cost ceiling |

All five change **real code paths** (planner/observer/parser wrappers), are
mutatable/crossable as categorical genes, and have measurable token/cost effects.

## Phenotype validation protocol

```
Fixed tasks + temperature 0 + same model
Genome A → Trace A (actions, tokens, cost, success)
Genome B → Trace B
Accept only if JS(action distributions) > threshold AND/OR cost differs
consistently across ≥2 repeats. Else gene is PROMPT_ONLY and must be labeled so.
```

Do **not** market this as RSI: no self-modifying code, no cross-generation
autonomous redesign. Label: *evolutionary multi-objective agent configuration
search*.
