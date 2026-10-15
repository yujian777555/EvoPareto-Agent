"""Frozen model rate table (Pilot1 hotfix)."""

from __future__ import annotations

from typing import Dict

RATE_VERSION = "deepseek-flash-2026-v1"

# USD per 1K tokens (estimated; provider billing not verified here).
RATES: Dict[str, Dict[str, float]] = {
    "deepseek-flash": {"prompt": 0.0001, "completion": 0.0002},
    "deepseek-chat": {"prompt": 0.0001, "completion": 0.0002},
}


def estimated_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    r = RATES.get(model)
    if r is None:
        raise ValueError(f"unknown model rate for {model!r}; rate_version={RATE_VERSION}")
    return (tokens_in / 1000.0) * r["prompt"] + (tokens_out / 1000.0) * r["completion"]
