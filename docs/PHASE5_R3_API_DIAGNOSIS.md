# Phase5-R3 — API Diagnosis (Task 1)

**Date:** session log · **Model:** `deepseek-flash` · **Mode:** direct (no proxy)

## 1. Balance probe (`GET /user/balance`)

| field | value |
|-------|-------|
| HTTP status | **200** |
| TTFB | 0.22 s |
| total latency | 0.22 s |
| balance fields present | **yes** (`available=true`) |
| secrets / account dump | **not logged** |

## 2. Chat probes (`thinking.type=disabled`, `max_tokens=64`)

| probe | model | HTTP | TTFB | total | body len | error |
|-------|-------|------|------|-------|----------|-------|
| non-stream | deepseek-flash | 200 | 0.19 s | 12.2 s | **0** | TimeoutError |
| stream | deepseek-flash | 200 | 0.19 s | 10.2 s | **0** | TimeoutError |
| non-stream | deepseek-v4-pro | 200 | 1.27 s | 11.3 s | **0** | TimeoutError |
| invalid JSON POST | any | 400 | 0.14 s | 0.14 s | err | parse error |

## 3. Proxy isolation

- `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` cleared
- `urllib.ProxyHandler({})` — empty proxy map
- `curl --noproxy "*"`
- `EVO_USE_PROXY` must be `1` to enable any proxy (default off)

## 4. Unified model ID

`DeepSeekBackend.model` = `deepseek-flash`  
`api_healthcheck()` / experiments use the same id.

## 5. Fault-isolation policy

- Empty body ≠ success
- On API failure: **stop real experiment**, do not exhaust budget on retries
- `run_real_llm_large.main()` aborts with `aborted=true` and `live_llm_evidence=false`

## 6. Diagnosis

Balance and routing are healthy. Chat completions return **HTTP 200 + empty body**
for all tested models — inference backend not returning completions from this
client/network. Official service remains unavailable for real experiments.

## 7. Next step when API recovers

```bash
python -m src.backend.diagnostics
python experiments/run_real_llm_large.py
```
