# Phase5-R3 — Large-scale Real LLM Validation

**Status:** protocol complete · **live-LLM evidence: PENDING** (DeepSeek chat API hang)

## Motivation

Upgrade DeepSeek validation from smoke (~300 calls) to **statistical**
multi-seed comparison of NSGA-III / +PEEM / +PEEM+PPEC.

## Setup

| item | value |
|------|-------|
| intended model | `deepseek-chat` |
| auth | `DEEPSEEK_API_KEY` (env) |
| proxy | `http://127.0.0.1:7897` (CONNECT tunnel via curl transport) |
| HTTP | `src/backend/http_client.py` (curl-first when proxied) |
| config | μ=8, G=4, tasks=10, **seeds {11,22,33}**, 3 methods |
| cache | isolated by task/genome/benchmark/seed/backend/model/preference |
| budget | ≤5000 API calls |

## API status at experiment time

```text
/v1/models          → 200 OK (~0.13s)
/v1/chat/completions → TIMEOUT (0 bytes)   ← both direct and via proxy
```

Malformed-JSON POSTs return 400 instantly; **valid chat requests hang**.
This is consistent with upstream inference/quota issues, not client auth
(models endpoint succeeds with the same key).

`results/real_llm_large/meta.json` stores the healthcheck transcript.
`cost_analysis.live_llm_evidence = false` for this run.

## Fallback protocol

When chat is down, the runner **auto-falls back to MockLLM** and labels
`backend_used=mock`, `live_llm_evidence=false` so tables are never
mis-cited as live-LLM results.

To obtain live evidence once API recovers:

```bash
export HTTPS_PROXY=http://127.0.0.1:7897
export HTTP_PROXY=http://127.0.0.1:7897
python experiments/run_real_llm_large.py
```

## Results (mock-protocol run, 3 seeds mean±std)

### ALFWorld

| Method | Success | HV | IGD | Cost |
|--------|---------|-----|------|------|
| B1 NSGA-III | 0.775 ± 0.074 | 0.722 ± 0.008 | 0.108 | 0.00118 |
| **B2 +PEEM** | **0.833 ± 0.047** | **0.747 ± 0.054** | 0.140 | 0.00112 |
| B3 +PEEM+PPEC | **0.833 ± 0.047** | **0.747 ± 0.054** | 0.140 | 0.00112 |

(See `results/real_llm_large/alfworld.json` for WebShop table & full stats.)

## Cost analysis fields

`total_api_calls`, `total_tokens`, `total_cost_usd`, `cache_hits`,
`cache_misses`, `within_budget`, `live_llm_evidence`.

## Comparison with simulator

Prior simulator PEEM success (Phase5-BM): ALFWorld 0.883, WebShop 0.500.
Current protocol run is consistent in *ordering* (PEEM ≥ NSGA-III).
Live-LLM comparison awaits API recovery.

## Limitations

1. **No live DeepSeek statistics in this commit** — chat completions hung
   during execution (`live_llm_evidence=false`).
2. Proxy transport (curl CONNECT) is ready; urllib stalls behind this proxy.
3. Do not cite mock-protocol tables as “real LLM experimental validation”.

## Paper impact (when live run completes)

- Moves real LLM from *demo* to *statistical experimental validation*.
- Until then, real-LLM evidence remains the Phase 4-R2 smoke (30 calls).
