# Phase5-R3 — DeepSeek API Recheck

**Model:** `deepseek-flash` · **Endpoint:** `https://api.deepseek.com/v1/chat/completions`  
**Payload:** `thinking.type=disabled`, `max_tokens=64`, `stream=false`, prompt “Reply with exactly: OK”

## Status: `API_AVAILABLE`

Success criterion: HTTP 200 + parseable JSON + non-empty `choices[0].message.content` + model id `deepseek-flash` + no mock/cache fallback.

---

## Step 1 — Config check

| item | value |
|------|-------|
| API key source | `DEEPSEEK_API_KEY` (not printed) |
| Base URL | `https://api.deepseek.com` |
| Chat path | `/v1/chat/completions` |
| Model | `deepseek-flash` |
| Proxy | default **off** (`EVO_USE_PROXY` opt-in) |

## Step 2–3 — Cross-validation

| method | HTTP | total time | body len | content | model | tokens in/out | ok |
|--------|------|------------|----------|---------|-------|---------------|-----|
| **curl** `--noproxy *` | 200 | 0.40 s | 453 | **`OK`** | deepseek-flash | 9 / 1 | ✅ |
| **OpenAI SDK** (httpx `trust_env=False`) | 200 | 1.89 s | — | **`OK`** | deepseek-flash | 35 / 14 | ✅ |
| **Project `DeepSeekBackend`** | 200 | 0.62 s | — | **`OK`** | deepseek-flash | 35 / 26 | ✅ |
| curl stream (not needed) | — | — | — | — | — | — | skipped |

Notes:
- Raw OpenAI SDK without `trust_env=False` failed with `APIConnectionError` (system proxy path).
- SDK rejected `thinking=` kwarg (`TypeError`) when passed as create() argument —
  API accepts the JSON field via curl/Backend; SDK test used default create().
- Metrics: HTTP status, wall time, body length, content non-empty, model id,
  prompt/completion tokens recorded. TTFB not separately instrumented on curl
  (`time_starttransfer` unused in final script); wall time is the completion latency.

## Step 3b — Confirmation (3×)

| run | total | content | tokens |
|-----|-------|---------|--------|
| 1 | 0.48 s | OK | 9/1 |
| 2 | 0.67 s | OK | 9/1 |
| 3 | 0.52 s | OK | 9/1 |

**Real success count: 5/5** (2 initial + 3 confirm) among curl/backend paths.

## Step 4 — Client issues

| question | finding |
|----------|---------|
| SDK vs curl vs Backend | all OK when proxy bypassed |
| params consistent | yes (`deepseek-flash`, max_tokens 64) |
| proxy | system proxy breaks SDK; curl `--noproxy` and Backend OK |
| prior 200+empty body | **resolved** (service recovered) |

## Step 5 — Result

**`API_AVAILABLE`**

- Real completions obtained (non-empty `OK`).
- No mock/cache used.
- **Large-scale experiments NOT started** (await Planner acceptance).

## Commands

```bash
python docs/_api_recheck.py
# or
python -c "from src.backend.base import DeepSeekBackend; print(DeepSeekBackend().generate('Reply with exactly: OK', budget=8).text)"
```
