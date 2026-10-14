# EvoPareto-Agent (Phase 0)

NSGA-III evolutionary foundation for **multi-objective agent configuration search**.

Phase 0 proves that an agent configuration genome can be optimized by a
many-objective evolutionary algorithm (NSGA-III) before connecting any real LLM
API. The paper narrative is an *evolutionary computation* method, not an
engineering demo.

## Motivation

Modern LLM agents expose many tunable knobs — planner style, memory policy,
reflection loop, tool usage, reasoning budget. These knobs trade off **task
performance**, **efficiency**, **cost**, **robustness**, and **autonomy**. A
single weighted scalar collapses the true Pareto structure.

This project evolves an *Agent Genome* with **NSGA-III** (Deb & Jain, 2014) so
that:

1. Many objectives (≥ 5) are handled natively via reference directions.
2. The output is a **Pareto front of agent configurations**, not one winner.
3. Later phases can plug in real LLM evaluators without changing the algorithm.

## Architecture

```text
src/
  agent/
    genome.py        # AgentGenome (DNA): serializable, comparable, mutable
    individual.py    # Individual: genome + fitness_vector + generation + metadata
  evolution/
    population.py    # Population manager: initialize / add / select / next_generation
    nsga3.py         # NSGA-III: non-dominated sorting + reference dirs + niching
    operators.py     # Agent-specific mutation / crossover
  evaluation/
    evaluator.py     # Toy multi-objective environment (no real LLM)
    objectives.py    # Objective conventions (max/min semantics)
  utils/
    pareto.py        # Pareto dominance / filter helpers
experiments/
  run_nsga3_demo.py  # End-to-end Phase 0 experiment
tests/               # pytest suite
results/             # generated artifacts
paper/               # reserved for later paper writing
```

### Agent Genome

```text
{
  planner_strategy,      # direct | cot | plan_and_solve | tree_search | reflexion
  memory_strategy,       # none | short_term | episodic | semantic | hybrid
  reflection_strategy,   # none | self_critique | pairwise | critic_model | iterative
  tool_policy,           # conservative | balanced | aggressive | tool_first | no_tools
  reasoning_budget       # 8 .. 128 (step 8)
}
```

### Objectives (5)

| name | direction | meaning |
|------|-----------|---------|
| performance | maximize | task success proxy |
| efficiency | maximize | cheap compute / latency |
| cost | **minimize** | monetary / token cost proxy |
| robustness | maximize | stability under noise |
| autonomy | maximize | less human intervention |

Internally NSGA-III minimizes; `to_minimization()` in
`src/evaluation/objectives.py` flips the maximize objectives.

### NSGA-III core (not a black-box library)

Implemented from scratch in `src/evolution/nsga3.py`:

1. **Fast non-dominated sorting** — rank fronts.
2. **Reference direction generation** — Das–Dennis simplex lattice
   (`C(H+M-1, M-1)` points). Supports ≥ 5 objectives.
3. **Normalization + association** — ideal/nadir intercepts, perpendicular
   distance to reference lines.
4. **Niching selection** — niche counts, random tie-breaking among min-count
   references (Jain rule).

### Operators

- `prompt_mutation` — planner strategy
- `memory_mutation` — memory policy
- `reflection_mutation` — reflection policy
- `tool_mutation` — tool usage policy
- `budget_mutation` — reasoning budget (snapped to step 8)
- `crossover` — uniform field crossover

## Quick start

```bash
# from repository root
python -m pytest -q

# run the Phase 0 demo experiment
python experiments/run_nsga3_demo.py
```

Artifacts land in `results/`:

- `population_history.json` — per-generation population stats
- `pareto_front.json` — non-dominated agent genomes + objective vectors
- `objective_scatter.png` (or `.txt` fallback) — objective visualization
- `run_summary.json` — run metadata

## Tests

`pytest` covers:

1. Genome serialization / comparison
2. Mutation correctness (each operator + bounds)
3. Population operations (initialize / add / select / next_generation)
4. NSGA-III selection (sorting, reference directions, niching, ≥5 objectives)
5. Pareto front correctness vs. brute-force filter

## Phase roadmap

| phase | goal | status |
|-------|------|--------|
| **Phase 0** | NSGA-III + AgentGenome + toy evaluation | ✅ current |
| Phase 1 | LLM Agent Genome + real evaluation (DeepSeek / GPT API) | |
| Phase 2 | Evolution Memory | |
| Phase 3 | Preference-aware adaptation | |
| Phase 4 | Benchmark + paper | |

Folder rename to `EvoPareto-Agent` is planned after Phase 4.

## Notes

- **No real LLM API** is called in Phase 0.
- **No benchmark suite** yet — that is Phase 4.
- **No paper prose** yet — keep this README as the technical contract.
- Algorithm correctness first; engineering demos come later.
