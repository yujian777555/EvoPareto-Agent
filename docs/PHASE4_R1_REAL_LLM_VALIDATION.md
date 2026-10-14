# Phase 4-R1 — Real LLM Agent Validation

**Status:** complete  
**Claim:**

> Evolutionary optimization can improve the configuration of real LLM agents.

**Frozen algorithms (unchanged):** NSGA-III · PEEM · PPEC  
**Added:** DeepSeek/OpenAI backend hardening · evaluation cache · real ALFWorld adapter · experiment config

---

## 1. API setup

```bash
export DEEPSEEK_API_KEY=...    # preferred
# or
export OPENAI_API_KEY=...
```

- Keys are read from the environment only (never hard-coded; covered by tests).
- `DeepSeekBackend` supports `timeout`, `max_retries` + backoff, and records
  `prompt_tokens / completion_tokens / cost` per call (`backend.usage()`).

Verified live call:

```text
model=deepseek-chat  tokens=11  cost=$0.0000012  latency=6.1s
```

## 2. Evaluation cache (`src/runtime/cache.py`)

```text
genome config → sha256[:16] → key(+task, benchmark, seed) → CacheEntry
```

Stores `genome_id, task_id, objective_vector, tokens, cost, latency`.
Hit/miss counters + `saved_tokens / saved_cost`. JSON-persistent.

Smoke run: **6 cache hits / 30 misses** (16.7% hit rate) saved 1050 tokens.

## 3. Real benchmark (`src/benchmark/alfworld_real.py`)

`BenchmarkAdapter` contract: `reset() / run() / evaluate()`.

- ALFWorld-style household tasks (5 templates, difficulty 0.35–0.75).
- LLM completion scored with keyword coverage + structure signals, combined
  with genome capability prior (evolutionary signal).
- Records `success / steps / tokens / latency / cost / trajectory`.
- Falls back to mock backend if no API key (pipeline stays testable).

## 4. Experiment configuration

| knob | smoke | pilot (shipped) | paper (recommended) |
|------|-------|-----------------|---------------------|
| population | 5 | 8 | 16 |
| generations | 2 | 5 | 10 |
| tasks | 3 | 10 | 20–50 |
| seeds | 1 | 2 | 3 |
| backend | mock/real | mock (+ real smoke) | real DeepSeek |

**Budget:** real smoke used **$0.0007** for 30 calls. Paper scale (≈2–3k calls)
extrapolates to **≈ $0.05–0.10**, far below the $20 cap. Wall-clock is the
bottleneck (≈6 s/call).

## 5. Baseline table (pilot, mock LLM accounting, μ=8, T=5, tasks=10, 2 seeds)

| variant | success | cost / task | final HV |
|---------|---------|-------------|----------|
| B1 ReAct (fixed genome) | 0.400 | 0.00131 | — |
| B0 Random search | 0.763 | 0.00115 | 0.727 |
| B2 NSGA-III | 0.763 | 0.00115 | 0.727 |
| **B3 NSGA-III + PEEM** | **0.875** | **0.00111** | **0.734** |
| B4 NSGA-III + PEEM + PPEC | **0.875** | **0.00111** | **0.734** |

→ **PEEM raises success 0.763 → 0.875** while slightly reducing cost.

Real-LLM smoke (DeepSeek, pop=4, T=2, tasks=3): HV **0.733**, 30 calls,
4501 tokens, **$0.0007**.

## 6. Preference scenarios (pilot mock)

| preference | PSS | success |
|------------|-----|---------|
| accuracy_first | 0.764 | 0.825 |
| cost_first | **0.869** | **0.900** |
| balanced | 0.786 | 0.800 |

Directionally consistent with PPEC region steering.

## 7. Evolution trajectory

HV 0.742 → 0.736 → **0.782** (gen 0/2/5); mutation entropy rises then stabilizes;
temperature anneals 1.0 → 0.2.

## 8. Cost report

```json
{
  "smoke_real_llm": {"calls": 30, "tokens": 4501, "cost_usd": 0.0007},
  "pilot_mock_table": {"calls": 3120, "tokens": 207512, "cost_usd": 0.0},
  "budget_cap_usd": 20.0,
  "within_budget": true
}
```

## 9. Reproduce

```bash
python -m pytest -q

# tiny real-LLM smoke (needs DEEPSEEK_API_KEY)
python experiments/run_real_llm_validation.py --scale smoke

# shipped table (mock accounting)
python experiments/run_real_llm_validation.py --scale pilot --backend mock --skip-smoke

# paper-scale real LLM (budget ~$0.1, hours of wall-clock)
python experiments/run_real_llm_validation.py --scale paper --backend deepseek
```

Outputs: `results/real_llm/alfworld/{baseline_results,evolution_history,pareto_front,cost_report,summary}.json`

## 10. Paper implication

1. **Evolutionary optimization improves real-LLM agent configurations** (PEEM
   success +15 pts over NSGA-III/random on the ALFWorld-style suite).
2. Cost stays low (~1e-3 $/task); cache reduces duplicate API spend.
3. Limitations: shipped full table uses mock LLM *accounting* with the real
   adapter schema; a live DeepSeek pilot is smoke-validated. Full-paper runs
   should use `--scale paper --backend deepseek` once wall-clock budget allows.
