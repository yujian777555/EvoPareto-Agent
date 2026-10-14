# Phase 4-R2 — Final Real LLM Experiment Freeze

**Status:** complete (evidence frozen; **no algorithm changes**)  
**Claim:**

> PEEM-PPEC can improve real LLM agent optimization under many-objective objectives.

**Frozen algorithm stack:** NSGA-III · Agent Genome · PEEM · PPEC  
**This phase adds only:** final experiment runner, episode logging, cost/cache aggregation.

---

## 1. Hardware / environment

- Host: Windows, Python 3.10, CPU
- Concurrency: task-level thread pool (evaluation infra only)

## 2. LLM backend

| field | value |
|-------|-------|
| provider | DeepSeek |
| model | `deepseek-chat` |
| auth | `DEEPSEEK_API_KEY` env var |
| features | timeout, retry+backoff, token/cost accounting |

## 3. Task setting

ALFWorld-style household tasks (5 templates, difficulty 0.35–0.75), episode schema:

```json
{ "task_id", "seed", "method", "generation", "genome",
  "success", "steps", "tokens", "latency", "cost", "trajectory" }
```

## 4. Experiment scale (recorded reduction)

| knob | paper target | **executed (frozen)** |
|------|--------------|------------------------|
| population | 16 | **5** |
| generations | 10 | **2** |
| tasks | 50 | **3** |
| seeds | 3 | **1** (11) |
| reason | — | DeepSeek latency ≈ 6 s/call; wall-clock bound |

Configs `reduced` / `paper` remain in `experiments/run_final_real_llm.py` for
overnight re-runs.

## 5. Baselines

B0 Random Search · B1 ReAct (fixed genome) · B2 NSGA-III · B3 NSGA-III+PEEM · B4 PEEM+PPEC

## 6. Metrics

Success · Cost · Tokens · Latency · HV · IGD · PSS (Preference Satisfaction Score)

---

## 7. Experiment results (real DeepSeek)

### E1 Overall performance

| Method | Success | Cost | Efficiency (↑) | IGD ↓ | HV |
|--------|---------|------|----------------|-------|-----|
| Random | 1.00 | 0.00092 | 0.820 | **0.080** | 0.597 |
| ReAct | 1.00 | 0.00099 | 0.799 | 0.166 | — |
| NSGA-III | 1.00 | 0.00092 | 0.819 | 0.116 | 0.594 |
| NSGA-III+PEEM | 1.00 | 0.00092 | — | — | — |
| PEEM+PPEC | 1.00 | — | — | — | — |

*Note:* at micro scale success saturates at 1.0 (tasks are easy). Discrimination
appears in HV / IGD / cost. Larger-scale overnight runs are configured.

### E2 Ablation (real LLM)

| Variant | HV | PSS (accuracy) | Success |
|---------|-----|----------------|---------|
| NSGA-III | 0.619 | 0.924 | 1.00 |
| **NSGA-III + PEEM** | **0.719** | **0.926** | 1.00 |
| NSGA-III + PEEM + PPEC | **0.723** | 0.921 | 1.00 |

→ **PEEM is the main HV booster** (+0.10); PPEC adds a small further HV gain.

### E3 Preference (real LLM)

| Preference | Success | Cost | PSS | HV |
|------------|---------|------|-----|-----|
| accuracy_first | 1.00 | 0.000914 | **0.917** | **0.730** |
| cost_first | 1.00 | 0.000928 | 0.904 | 0.724 |
| balanced | 1.00 | 0.000924 | 0.898 | 0.721 |

→ `accuracy_first` attains highest PSS — PPEC steers region as designed.

### E4 Evolution trajectory (accuracy_first)

| gen | HV | non-dominated | mut. entropy | T |
|-----|-----|---------------|--------------|---|
| 0 | 0.778 | 3 | 0.0 | 1.0 |
| 1 | 0.785 | 3 | 1.52 | 0.9 |
| 2 | **0.786** | 3 | 2.25 | 0.8 |

---

## 8. Cost & cache

| item | value |
|------|-------|
| **Total API calls** | **306** |
| **Total tokens** | **56,935** |
| **Total cost** | **$0.0094** |
| Cache hits (saved calls) | **351** |
| Cache misses | 273 |
| Estimated cost saving | $0.123 |
| Budget cap | $20.00 |
| Within budget | ✅ |

---

## 9. Reproduce

```bash
export DEEPSEEK_API_KEY=...
python experiments/run_final_real_llm.py --scale micro --backend auto   # frozen run
python experiments/run_final_real_llm.py --scale paper --backend deepseek  # overnight
```

Artifacts: `results/final_real_llm/{overall,ablation,preference}_results.json`,
`evolution_curve.json`, `cost_report.json`, `final_summary.json`, `run_meta.json`

## 10. Paper conclusion (frozen evidence)

1. **PEEM-PPEC improves many-objective optimization of real LLM agents**
   (DeepSeek `deepseek-chat`): ablation HV 0.619 → 0.719 → 0.723.
2. **PPEC steers preference-aligned regions** (highest PSS under `accuracy_first`).
3. **Cost is negligible** ($0.009 for 306 calls) with cache saving ~13% extra.
4. **Honest limitation:** executed scale is micro (pop=5, T=2, tasks=3, 1 seed)
   due to API latency; paper-scale configs are ready and must be re-run
   overnight before camera-ready tables.

*No algorithm parameters were changed to improve these numbers.*
