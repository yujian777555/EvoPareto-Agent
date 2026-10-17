# GSM8K Data Split & Request Budget (Task 3)

**Evidence class:** OFFICIAL_DATA (task indices) + HYPOTHESIS_ONLY (budget plan)
**Module:** `src/benchmark/gsm8k_split.py`
**Artifacts:** `results/stage3_0_p1_r2a/gsm8k_split_manifest.json`,
`results/stage3_0_p1_r2a/budget_identity.json`

## Split (frozen, hash-locked)

| Partition | Indices | n | Role |
|---|---|---:|---|
| search | 0–19 | 20 | evolutionary selection ONLY |
| validation | 20–29 | 10 | in-loop validation |
| test | 30–49 | 20 | final held-out, never selection |

- overlap search∩test = `[]`
- overlap validation∩test = `[]`
- `selection_uses_test_set = False`
- split_sha256 = `bd168b930b2f75c1d5b18e35ffdfa28033253521a3d5a3abf1f8fc4f236c1472`

**Official test set is never used as evolution selection evidence.**

## Model & price (re-verified 2026-10-16)

| Field | Value |
|---|---|
| model_id | **deepseek-flash** |
| model_version | **DeepSeek-V4.1-Flash** |
| pricing_source | https://api-docs.deepseek.com/quick_start/pricing |
| input cache-miss peak | $0.30 / 1M tokens |
| output peak | $1.20 / 1M tokens |

## Request & token caps

| Cap | Value |
|---|---:|
| max input tokens / request | 2,000 |
| max output tokens / request | 500 |
| max total input tokens | 2,000,000 |
| max total output tokens | 200,000 |
| max physical requests | **300** |
| max total cost | **$5.0** |
| worst-case cost (peak, cache-miss) | $0.84 |
| under cap | True |

**Every request and every failure retry is written to the request_ledger**
(`retries_counted_in_ledger = True`).

## Network policy

{
  "deepseek_physical_requests": "DIRECT_NO_SYSTEM_PROXY",
  "detail": "DeepSeek HTTP calls must ignore the system/global proxy (no HTTP_PROXY/HTTPS_PROXY/ALL_PROXY) and connect straight to api.deepseek.com. The Provider Gateway and the code-execution sandbox keep their own separate security boundaries."
}

Provider base URL: `https://api.deepseek.com` — direct connection, no
system global proxy. The Provider Gateway and the code-execution sandbox retain
their own separate security boundaries.

## Verdict

**VALIDATION_TEST_SPLIT: PASS (strictly separated)**
**PRICE_VERIFIED: 2026-10-16**
**HARD_CAP: $5**
