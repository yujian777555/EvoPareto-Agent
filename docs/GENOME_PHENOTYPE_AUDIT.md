# Agent Genome Phenotype Audit

**Question:** do the five genes change *real execution behavior*, or only labels/prompts?  
**Native path under review:** `InteractiveAgent` via `EpisodeRunner` (Pilot 1 / ALFWorld).  
**Evidence sources:** `src/runtime/interactive_agent.py`, `src/runtime/behavioral_agent.py`, `src/agent/genome.py`.  
**Real API calls: 0.** Matrix JSON: `results/pilot1_postmortem/genome_phenotype_matrix.json`.

---

## 1. Phenotype validity matrix

| Genome Gene | Changes Prompt | Changes Execution Mechanism | Measurable Behavior Delta | Evidence Level |
|---|---|---|---|---|
| planner_strategy | Yes (label + 3 special strategy lines) | **No** on native path | `cot`/`direct` produce zero instruction difference; `plan_and_solve`/`tree_search`/`reflexion` only append one strategy sentence | **PROMPT_ONLY** |
| memory_strategy | Yes (History block) | **Yes** — MemoryStore read/write rules | `none` → 0 lines; `short_term` → 1 last obs; `episodic/semantic/hybrid` → up to 3 | **CODE_CONFIRMED** |
| reflection_strategy | Yes (label) | **Yes but degenerate** — only parse-failure retry | `none` vs non-none differs; `self_critique`/`pairwise`/`critic_model`/`iterative` are **behaviorally identical** | **CODE_CONFIRMED** |
| tool_policy | Yes (label) | **No** on native path | `self.allow` never consulted for ALFWorld admissible commands; ALLOW_TOOLS names (calculator/file_*) are not ALFWorld verbs | **CODE_CONFIRMED (as NO-OP)** |
| reasoning_budget | Yes (remaining-steps line) | **Yes** — BudgetMeter | `max_steps=round(horizon*(0.5+b/128))`, `max_tokens=max(64,b*12)`; changes length/cost, **not** per-step quality | **CODE_CONFIRMED** |

`PROMPT_ONLY ≠ useless`, but it must not be sold as an execution-mechanism change.

## 2. Per-gene source verification

### 2.1 planner_strategy — PROMPT_ONLY on native path

```python
# interactive_agent.select_action
prompt_lines.append(f"Planner: {self.genome.planner_strategy}")
if self.genome.planner_strategy == "plan_and_solve":
    prompt_lines.append("Strategy: decompose goal into sub-steps then act.")
elif self.genome.planner_strategy == "tree_search":
    ...
elif self.genome.planner_strategy == "reflexion":
    ...
# "cot" and "direct": NO extra line at all
```

- No plan is stored, decomposed, or executed in `InteractiveAgent`.
- `BehavioralAgent._plan` (step tags `act:`/`decompose:`/…) is **not** on the
  native ALFWorld path (`EpisodeRunner` uses `InteractiveAgent`).
- Therefore two genomes differing only in `planner_strategy ∈ {direct, cot}`
  are **indistinguishable except for one label string** in the prompt.

### 2.2 memory_strategy — real execution difference

| strategy | write | read | prompt History size |
|---|---|---|---|
| none | disabled | [] | absent |
| short_term | append `obs:<120>` | `items[-1:]` | 1 line |
| episodic / semantic / hybrid | append `obs:<120>` | `items[-3:]` | up to 3 lines |

Caveat: content is **only** the observation preview — not actions or outcomes.
So "episodic" does not actually store episodes; it stores the last 3 observations.

### 2.3 reflection_strategy — one mechanism, four names

```python
if action is None and self.genome.reflection_strategy != "none":
    # identical retry prompt for every non-none strategy
```

- Trigger = parse failure only (not stagnation, not poor progress).
- `self_critique` / `pairwise` / `critic_model` / `iterative` share one code path.
- Phenotypically the gene has **2 levels** (none vs not-none), not 5.

### 2.4 tool_policy — no-op on native ALFWorld

```python
self.allow = ALLOW_TOOLS.get(genome.tool_policy, frozenset())
# select_action() NEVER reads self.allow
```

`ALLOW_TOOLS` gates tools like `calculator`, `search`, `file_read` in
`BehavioralAgent.invoke_tool` — a different runtime not used by Pilot 1.
ALFWorld command space is whatever `admissible_commands` the environment returns.

**Research consequence:** mutating `tool_policy` cannot change native ALFWorld
behavior. It is a free variable for NSGA-III unless the evaluation path is changed.

### 2.5 reasoning_budget — real, but length-only

```
budget=64, horizon=30 → max_steps=30, max_tokens=768
budget=8,  horizon=30 → max_steps=16, max_tokens=96
budget=128, horizon=30 → max_steps=45→ but horizon loop is 30
```

- Controls **how long** the episode runs (and thus cost).
- Does **not** improve single-step decisions.
- Reflection charges the same step pool → fewer actions if reflection fires.

## 3. Counterfactual / offline diagnostics (no API)

Run with Mock LLM (wiring only — **not** real success rates):

| Diagnostic | Expected if gene is real | Status |
|---|---|---|
| Memory lines in prompt: none vs short_term vs episodic | 0 / 1 / ≤3 | CODE_CONFIRMED |
| Reflection fires on parse failure only | stagnation loop never reflects | CODE_CONFIRMED |
| tool_policy change → ALFWorld admissible set | unchanged | CODE_CONFIRMED |
| budget=8 vs 64 → max_steps | 16 vs 30 | CODE_CONFIRMED |
| planner cot vs direct → instruction text | identical except label | CODE_CONFIRMED |

These can be unit-tested deterministically; they are already encoded in
`results/pilot1_postmortem/genome_phenotype_matrix.json`.

## 4. Evolutionary risk (must enter experiment design)

If performance is mostly `won=0` across genomes, the two objectives collapse to
**cost minimization**. Then `reasoning_budget` dominates (smaller budget → cheaper
failure) and NSGA-III/PEEM/PPEC differences become untestable.

Additionally, two of five genes (`planner_strategy` fully, `tool_policy` fully)
cannot move native performance at all → effective genotype dimensionality is
≈ 2–3, not 5.

## 5. Summary answer

| Claim | Verdict |
|---|---|
| All 5 genes change execution | **False** |
| At least 2 genes change execution | **True** (memory, reasoning_budget) |
| reflection gene has 5 distinct behaviors | **False** (2: none vs retry-on-parse-fail) |
| tool_policy affects ALFWorld | **False** (no-op) |
| planner_strategy affects native planning | **False** (prompt label / one sentence) |

Formal experiments must either (a) restrict mutation to the behaviorally real
subset and report the effective search space, or (b) upgrade the phenotypes
**as a shared baseline** for all compared methods before any PEEM/PPEC claim.
