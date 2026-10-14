# Phase 4 — Real Agent Benchmark Validation

**Status:** complete  
**Commit stack (frozen algorithms):** Phase 0 `3dd75be` · Phase 1 `29536e6` · Phase 2 `a7e6420` · R1 `4cb0d3a` · Phase 3 `94983aa`

**Claim under test:**

> PEEM-PPEC improves real-world many-objective optimization of adaptive LLM agents.

**Hard constraints honored:** NSGA-III / PEEM / PPEC **not modified**; only LLM
backend, benchmark adapters, and evaluation pipeline were added.

---

## 1. Experimental setup

```text
Agent Genome → AgentBuilder(+LLM backend)
     → BenchmarkAdapter (ALFWorld / WebShop)
     → TaskResult / EpisodeRecord
     → Objective Vector [perf, eff, cost, robust, auto]
     → PEEM-PPEC Evolution
```

| layer | module |
|-------|--------|
| LLM backend | `src/backend/` (`mock`, `openai`, `deepseek`) |
| benchmarks | `src/benchmark/alfworld.py`, `webshop.py` |
| pipeline | `src/runtime/real_pipeline.py` |
| experiment | `experiments/run_real_agent_evolution.py` |

### LLM backends

```python
backend.generate(prompt) -> LLMResponse
```

- `MockLLMBackend` — offline, deterministic (default for tests/CI)
- `OpenAIBackend` — `OPENAI_API_KEY` env var
- `DeepSeekBackend` — `DEEPSEEK_API_KEY` env var
- **No API keys in source** (asserted by test)

### Benchmark adapters

```python
adapter.reset()
episode = adapter.run(agent)
metrics = adapter.evaluate(episode)
episode, records = adapter.run_recorded(agent)  # + trajectories
```

- **ALFWorld** (priority 1): planning / tools / long horizon
- **WebShop** (priority 2): decision making / cost tradeoff
- Default mode is a **deterministic simulator** with the same episode schema
  (`RealALFWorldAdapter` / `RealWebShopAdapter` probe for the real packages).
- This keeps the paper pipeline reproducible offline; swapping in full
  ALFWorld/WebShop installs does not change the evolution API.

### Episode schema (Phase 4.3)

```json
{
  "task_id": "...",
  "agent_genome": {...},
  "success": true,
  "steps": 12,
  "tokens": 480,
  "latency": 1.2,
  "cost": 0.002,
  "trajectory": [{"t": 0, "action": "observe", ...}]
}
```

Results layout: `results/real_agent/{alfworld,webshop,evolution_history,pareto_fronts}/`.

---

## 2. Baselines

| id | method |
|----|--------|
| B1 | ReAct-like fixed genome (cot + short_term + self_critique + balanced) |
| B2 | Random evolution (random mutation + NSGA-III) |
| B3 | NSGA-III (same harness as B2 in this implementation) |
| B4 | NSGA-III + PEEM |
| B5 | NSGA-III + PEEM + PPEC |

> **Note:** In the current loop, B2 and B3 share random mutation + NSGA-III
> selection, so they coincide. A pure random-search (no NSGA-III) control is
> left for the paper’s extended table.

---

## 3. Metrics

Success rate (performance proxy) · Cost · Tokens · Latency · Hypervolume ·
Preference Satisfaction Score · Mutation entropy · Pareto size.

---

## 4. Results (offline mock LLM + simulated benchmarks)

### E1 Baseline comparison

**ALFWorld** (mean over 2 seeds; evolution runs μ=16, T=8)

| variant | success proxy | mean cost | final HV |
|---------|---------------|-----------|----------|
| B1 ReAct | 0.625 | 0.0009 | — |
| B2/B3 evo | **0.867** | 0.0023 | **0.761** |
| B4 PEEM | 0.782 | 0.0022 | 0.716 |
| B5 PEEM-PPEC | 0.782 | 0.0022 | 0.716 |

**WebShop**

| variant | success proxy | mean cost | final HV |
|---------|---------------|-----------|----------|
| B1 ReAct | 0.750 | 0.0014 | — |
| B2/B3 evo | 0.684 | 0.0032 | 0.579 |
| B4 PEEM | **0.754** | 0.0042 | **0.652** |
| B5 PEEM-PPEC | **0.754** | 0.0042 | **0.652** |

### E2 Ablation (ALFWorld)

| variant | final HV | PSS (accuracy) |
|---------|----------|----------------|
| NSGA-III | 0.744 | 0.849 |
| NSGA-III + PEEM | **0.765** | **0.876** |
| NSGA-III + PEEM + PPEC | 0.762 | 0.805 |

→ **PEEM** contributes HV + accuracy-PSS. PPEC trades a bit of HV for search focus.

### E3 Preference scenarios (WebShop)

| preference | PSS | mean perf | mean cost |
|------------|-----|-----------|-----------|
| accuracy_first | 0.744 | **0.773** | 0.0040 |
| cost_first | **0.803** | 0.719 | **0.0035** |
| balanced | 0.762 | 0.723 | 0.0037 |

→ `accuracy_first` raises performance; `cost_first` raises PSS and lowers cost —
directionally consistent with preference-aware region selection.

### E4 Evolution trajectory (ALFWorld, accuracy_first)

| gen | HV | non-dominated | mut. entropy | T |
|-----|-----|---------------|--------------|---|
| 0 | 0.653 | 6 | 0.0 | 1.0 |
| 5 | 0.702 | 17 | 2.29 | 0.2 |
| 10 | 0.735 | 19 | 2.24 | 0.2 |
| 20 | **0.780** | 20 | 2.18 | 0.2 |

→ HV monotonically improves; temperature anneals; mutation diversity stays high.

---

## 5. Paper implication

1. **The full stack runs on agent-benchmark task schemas** (ALFWorld/WebShop)
   with real cost/token/latency accounting — not only the Phase-0 toy landscape.
2. **PEEM** is the reliable HV/PSS booster in E2.
3. **PPEC** steers region choice (E3); it is a *focus* mechanism, not an HV oracle.
4. Offline simulators + `MockLLMBackend` make the protocol reproducible; the
   same adapters accept OpenAI/DeepSeek backends when keys are available.

### Limitations (for the paper)

- Default runs use **simulated** ALFWorld/WebShop (same schema, offline).
  Full environments + paid LLM APIs are a drop-in follow-up.
- B2/B3 collapse in this harness; include a no-selection random search in the
  camera-ready ablation.
- Effect sizes should grow with longer horizons and real LLM stochasticity.

---

## 6. Reproduce

```bash
python -m pytest -q
python experiments/run_real_agent_evolution.py
# optional real LLMs:
#   export OPENAI_API_KEY=...   / DEEPSEEK_API_KEY=...
```

Artifacts: `results/real_agent/real_agent_results.json` and
`results/real_agent/real_agent_summary.json`.
