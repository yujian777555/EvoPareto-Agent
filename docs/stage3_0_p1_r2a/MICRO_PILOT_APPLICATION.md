# Micro Pilot Application (NOT executed)

Model: **deepseek-flash** · pricing source: api-docs.deepseek.com
(peak $0.30/1M in, $1.20/1M out) · verified 2026-10-16.

Benchmark: GSM8K official tasks (20 tasks). Search: 3 rounds × sample=2.

| Cap | Value |
|---|---|
| max_candidates | 3 |
| max_physical_requests | 300 |
| max_input_tokens | 2,000,000 |
| max_output_tokens | 200,000 |
| max_total_cost | **$5.00** |

Derived from: optimize LLM ~1 call/round (2k in, 0.5k out) + exec LLM
3×20×2 calls (~800 in, 200 out each) ≈ 123 logical ≈ 300 HTTP with retries.
Worst-case cost ≈ 2.2M tokens × peak ≈ $0.93 → **$5 cap is safe**.

Stop: budget cap · billing-blocked · crash (keep partial). All requests via
Provider Gateway + SQLite ledger. Sandbox: docker --network none.
