"""Authoritative DeepSeek rate table (Pilot1 preflight).

Source (official):
  https://api-docs.deepseek.com/quick_start/pricing/
Verified: 2026-10 (see RATE_SOURCE_VERIFIED_ON).

Policy for this engineering pilot — CONSERVATIVE PEAK:
  input tokens  = peak price, cache MISS  ($0.30 / 1M)
  output tokens = peak price              ($1.20 / 1M)

Off-peak / cache-hit discounts are deliberately ignored so local budget
estimates never understate spend. This is NOT the provider's final invoice.

Only the official model name is priced. Unknown / retired names get
UNKNOWN_RATE — never a cheaper fallback rate.
"""

from __future__ import annotations

from typing import Dict

RATE_VERSION = "deepseek-flash-2026-10-peak-conservative-v1"
RATE_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing/"
RATE_SOURCE_VERIFIED_ON = "2026-10"

# USD per 1M tokens — peak conservative (cache-miss input, peak output).
PEAK_INPUT_CACHE_MISS_PER_1M = 0.30
PEAK_OUTPUT_PER_1M = 1.20

# Legacy alias kept as CONSTANTS ONLY (per-1K view of the same numbers).
PEAK_INPUT_PER_1K = PEAK_INPUT_CACHE_MISS_PER_1M / 1000.0  # 0.0003
PEAK_OUTPUT_PER_1K = PEAK_OUTPUT_PER_1M / 1000.0  # 0.0012

# Single authoritative model → rate map. Keys must match official model ids.
RATES: Dict[str, Dict[str, float]] = {
    # official id: deepseek-flash (DeepSeek-V4.1-Flash)
    "deepseek-flash": {
        "prompt_per_1m": PEAK_INPUT_CACHE_MISS_PER_1M,
        "completion_per_1m": PEAK_OUTPUT_PER_1M,
        # per-1K convenience mirrors used by older call sites
        "prompt": PEAK_INPUT_PER_1K,
        "completion": PEAK_OUTPUT_PER_1K,
    },
}

KNOWN_MODELS = tuple(RATES)


def estimated_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Conservative peak estimate. Raises for unknown models (no cheap fallback)."""
    r = RATES.get(model)
    if r is None:
        raise ValueError(f"unknown model rate for {model!r}; rate_version={RATE_VERSION}")
    return (tokens_in / 1_000_000.0) * r["prompt_per_1m"] + (tokens_out / 1_000_000.0) * r[
        "completion_per_1m"
    ]


def rate_metadata() -> Dict[str, object]:
    return {
        "rate_version": RATE_VERSION,
        "source": RATE_SOURCE,
        "verified_on": RATE_SOURCE_VERIFIED_ON,
        "policy": "peak_conservative_cache_miss_input_peak_output",
        "peak_input_cache_miss_per_1m": PEAK_INPUT_CACHE_MISS_PER_1M,
        "peak_output_per_1m": PEAK_OUTPUT_PER_1M,
        "known_models": list(KNOWN_MODELS),
    }
