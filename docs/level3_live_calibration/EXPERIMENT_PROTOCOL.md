# Level 3 Live Calibration Protocol

**Authorization:** first limited real DeepSeek calibration (NOT the $5 pilot).

## Hard limits (all simultaneous)

| Cap | Value |
|---|---:|
| MODEL | deepseek-flash (DeepSeek-V4.1-Flash-1017) |
| THINKING | disabled |
| MAX_PHYSICAL_HTTP_REQUESTS | 10 |
| MAX_REAL_API_COST_USD | **0.10** |
| MAX_INPUT_PER_REQUEST | 8000 |
| MAX_OUTPUT_PER_REQUEST | 500 |
| MAX_TOTAL_INPUT_TOKENS | 80000 |
| MAX_TOTAL_OUTPUT_TOKENS | 5000 |
| CONCURRENCY | 1 |
| AUTO_EXPAND_BUDGET | FALSE |

Any limit reached or anomaly -> persistent stop. No Run ID / DB / restart reset.

## Request shape (sent as required)

```json
{
  "model": "deepseek-flash",
  "thinking": {"type": "disabled"},
  "max_tokens": 500,
  "messages": [{"role": "user", "content": "..."}]
}
```

Base URL `https://api.deepseek.com`, direct connection (system proxy bypassed).
API key from `DEEPSEEK_API_KEY` env var only — never committed.

## Calibration sequence (GSM8K train only)

1. Plain math task — non-empty, parseable response
2. AFlow-shaped Optimizer prompt — complete XML mutation
3. Graph / Prompt syntax validation
4. Docker + IPC execution of the **real generated** candidate
5. Host trusted scorer (gold never leaves the host)

## Stop conditions

cost/requests exhausted · API auth/billing anomaly · thinking mismatch ·
truncated response · incomplete structured output · usage anomaly ·
budget/IPC isolation failure · test-set leakage · sandbox cannot execute code.

Wrong math answers are scored zero and kept — never rewritten.
