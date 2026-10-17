# GSM8K Micro-Pilot Protocol (Task 5) — FROZEN, NOT EXECUTED

**Status: FROZEN_NOT_EXECUTED · REAL_LLM_CALLS = 0 · REAL_API_COST = $0**

## Split (correction)

Earlier drafts used official **test** indices for search. Forbidden. The frozen
protocol is:

| Partition | Official split | Indices | n | Role |
|---|---|---|---:|---|
| search | **train** | 0-19 | 20 | evolutionary selection |
| validation | **train** | 20-29 | 10 | in-loop validation |
| final test | **test** | 0-19 | 20 | held-out, never selection |

- selection_uses_official_test_set = **False**
- split_sha256 = `9a9cbdc9684c2488cf6a93e98fdeb4050513b4d5390e3b29b0e449b7bb2e790e`
- task IDs: `gsm8k-train-####` vs `gsm8k-test-####` (disjoint namespaces)

## Model and price (re-verified 2026-10-16)

| Field | Value |
|---|---|
| model_id | **deepseek-flash** |
| model_version | **DeepSeek-V4.1-Flash** |
| pricing_source | https://api-docs.deepseek.com/quick_start/pricing |

## Caps (limits, not targets)

| Cap | Value |
|---|---:|
| max physical HTTP | **300** (retries counted) |
| max input tokens | 2000000 |
| max output tokens | 200000 |
| per-request tokens | 2000 in / 500 out |
| **hard cost cap** | **$5.0** |
| worst-case (peak cache-miss) | $0.84 |

## Network

{
  "deepseek_physical_requests": "DIRECT_NO_SYSTEM_PROXY",
  "detail": "DeepSeek HTTP calls ignore HTTP_PROXY/HTTPS_PROXY/ALL_PROXY and connect straight to api.deepseek.com. The Provider Gateway budget gate and the Docker execution sandbox keep their own separate security boundaries; direct connectivity does not bypass either of them."
}

## Frozen protocol rules

- initial Workflow frozen (official GSM8K round_1 template)
- every candidate recorded
- mutations checked executable
- **no test-set feedback into search**
- stop on budget cap / billing blocked / crash (keep partial)

## Verdict

**GSM8K_TRAIN_VALIDATION_TEST_SPLIT = FROZEN**
