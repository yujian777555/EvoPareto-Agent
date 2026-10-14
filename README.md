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
    archive.py       # Phase 2: EvolutionRecord / EvolutionArchive (optimizer memory)
    experience.py    # Phase 2: MutationExperience statistics
    credit_assignment.py  # Phase 2.5: composite mutation value
    diversity.py     # Phase 2.5: crowding / spacing / diversity contribution
    pareto_experience.py  # Phase 2.5: PEEM (decay + Pareto-aware utility)
    pareto_credit.py # Phase 2.5-R1: rank-based Pareto contribution
    normalization.py # Phase 2.5-R1: per-generation z-score
    delayed_credit.py # Phase 2.5-R1: delayed survival / Pareto gain
    adaptive_mutation.py  # Phase 2/2.5-R1: controller + temperature softmax
    memory_evolution.py   # Phase 2/2.5-R1/3: memory-aware / robust PEEM / preference loop
    preference.py         # Phase 3: PreferenceVector + structured encoder
    reference_adapter.py  # Phase 3: preference-guided reference directions
    preference_controller.py  # Phase 3: PPEC (set_preference / region / score)
  runtime/           # Phase 1: genome -> agent -> task results
    task.py          # TaskSpec / TaskSuite
    result.py        # TaskResult / EpisodeResult
    agent_builder.py # AgentBuilder + Agent + LLMBackend protocol
    agent_runner.py  # unified agent.run(task) runner
    pipeline.py      # genome -> objectives + run_agent_evolution
    real_pipeline.py # Phase 4: real benchmark evaluation pipeline
  backend/
    base.py          # Phase 4: LLMBackend + Mock/OpenAI/DeepSeek
    mock.py
    openai_backend.py
    deepseek_backend.py
  benchmark/
    base.py          # Benchmark ABC
    mock_benchmark.py
    base_adapter.py  # Phase 4: BenchmarkAdapter + EpisodeRecord
    alfworld.py      # Phase 4: ALFWorld adapter
    webshop.py       # Phase 4: WebShop adapter
  evaluation/
    evaluator.py     # Toy multi-objective environment (Phase 0)
    objective_evaluator.py  # TaskResult -> paper objective vector (Phase 1)
    metrics.py       # Phase 2/2.5: hypervolume, IGD, spacing, mutation entropy
    objectives.py    # Objective conventions (max/min semantics)
  utils/
    pareto.py        # Pareto dominance / filter helpers
experiments/
  run_nsga3_demo.py              # Phase 0 demo
  run_agent_evolution_demo.py    # Phase 1 demo
  run_evolution_memory_demo.py   # Phase 2: memory vs random mutation
  run_peem_demo.py               # Phase 2.5: PEEM vs baselines (E1-E4)
tests/               # pytest suite
results/             # generated artifacts
paper/               # reserved for later paper writing
docs/                # phase audit + design docs
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

# Phase 0: NSGA-III on toy landscape
python experiments/run_nsga3_demo.py

# Phase 1: agent genome -> runtime -> benchmark -> evolution
python experiments/run_agent_evolution_demo.py

# Phase 2: evolution experience memory vs random mutation
python experiments/run_evolution_memory_demo.py

# Phase 2.5: PEEM (Pareto-aware) vs baselines
python experiments/run_peem_demo.py

# Phase 2.5-R1: Robust PEEM (rank credit + delayed + temperature)
python experiments/run_robust_peem_demo.py

# Phase 3: preference-aware Pareto evolution controller
python experiments/run_preference_demo.py

# Phase 4: real agent benchmark validation (ALFWorld / WebShop)
python experiments/run_real_agent_evolution.py

# Phase 4-R1: real LLM validation (DeepSeek/OpenAI + cache)
python experiments/run_real_llm_validation.py --scale smoke

# Phase 4-R2: final frozen real-LLM experiments
python experiments/run_final_real_llm.py --scale micro --backend auto
```

Artifacts land in `results/`:

- Phase 0: `population_history.json`, `pareto_front.json`, `objective_scatter.png`
- Phase 1: `agent_population_history.json`, `agent_pareto_front.json`, `agent_evolution_summary.json`
- Phase 2: `evolution_memory_results.json`, `evolution_memory_summary.json`
- Phase 2.5: `peem_results.json`, `peem_summary.json`
- Phase 2.5-R1: `robust_peem_results.json`, `robust_peem_summary.json`
- Phase 3: `preference_results.json`, `preference_summary.json`
- Phase 4: `real_agent/` (alfworld, webshop, evolution_history, pareto_fronts)

Phase 4 LLM backends: `MockLLMBackend` (offline default) or set
`OPENAI_API_KEY` / `DEEPSEEK_API_KEY` for real LLMs.

## Tests

`pytest` covers:

**Phase 0**

1. Genome serialization / comparison
2. Mutation correctness (each operator + bounds)
3. Population operations (initialize / add / select / next_generation)
4. NSGA-III selection (sorting, reference directions, niching, ≥5 objectives)
5. Pareto front correctness vs. brute-force filter

**Phase 1**

6. Genome → Agent creation
7. Agent runtime execution (`agent.run_task`)
8. Benchmark adapter (`MockBenchmark`)
9. Objective vector correctness (mixed max/min)
10. End-to-end evolution pipeline

**Phase 2**

11. Evolution archive (record / serialize / persist)
12. Mutation experience statistics & scores
13. Adaptive mutation probability (normalize / deterministic)
14. Archive & experience updates after evolution
15. End-to-end memory-aware pipeline

**Phase 2.5 (PEEM)**

16. Credit calculation (improvement / HV / diversity / survival)
17. Hypervolume contribution
18. Diversity calculation (crowding / spacing)
19. Experience decay (configurable λ)
20. PEEM-aware adaptive probability

**Phase 2.5-R1 (Robust PEEM)**

21. Rank-based Pareto contribution estimator
22. Per-generation z-normalization
23. Delayed credit (future survival / Pareto gain)
24. Temperature-softmax mutation sampling
25. Long-horizon robust evolution loop

**Phase 3 (Preference-aware PPEC)**

26. PreferenceVector encoding / normalization / serialization
27. Reference direction adaptation
28. Preference satisfaction scoring
29. PreferenceController API
30. End-to-end preference-guided evolution

**Phase 4 (Real benchmark validation)**

31. LLM backend abstraction (mock / OpenAI / DeepSeek, env-var keys)
32. ALFWorld / WebShop adapters (reset / run / evaluate)
33. Episode records + cost / token / latency tracking
34. Real benchmark evolution pipeline
35. Baseline / ablation / preference / trajectory experiments

## Phase roadmap

| phase | goal | status |
|-------|------|--------|
| **Phase 0** | NSGA-III + AgentGenome + toy evaluation | ✅ frozen (`3dd75be`) |
| **Phase 1** | Agent runtime + benchmark adapter + objective evaluator | ✅ frozen (`29536e6`) |
| **Phase 2** | Evolution Experience Memory (optimizer memory) | ✅ frozen (`a7e6420`) |
| **Phase 2.5** | **PEEM**: Pareto-aware mutation utility | ✅ frozen (`0b770ac`) |
| **Phase 2.5-R1** | **Robust PEEM**: rank credit + delayed + temperature | ✅ frozen (`4cb0d3a`) |
| **Phase 3** | **PPEC**: preference-aware Pareto search | ✅ frozen (`94983aa`) |
| **Phase 4** | **Real benchmark validation** (ALFWorld / WebShop) | ✅ frozen (`647be4f`) |
| **Phase 4-R1** | **Real LLM validation** (DeepSeek + cache) | ✅ frozen (`2a703df`) |
| **Phase 4-R2** | **Final real-LLM experiment freeze** | ✅ current |
| Phase 5 | Paper writing + CCF-B submission package | |

See `docs/PHASE0_FINAL_AUDIT.md` … `docs/PHASE4_R2_FINAL_EXPERIMENT.md`.

Folder rename to `EvoPareto-Agent` is planned after Phase 4.

## Notes

- Phase 0–2 use offline mock evaluation only; Phase 4 adds real LLM backends
  (mock default; OpenAI / DeepSeek via env-var API keys).
- ALFWorld / WebShop adapters default to offline simulators with the real
  episode schema; full environments plug into the same API.
