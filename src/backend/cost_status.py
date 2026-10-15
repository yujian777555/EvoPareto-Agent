"""Cost status + fail-closed estimation (Pilot1 preflight).

Rate numbers come from ONE authoritative module: src.backend.rates.
Transport / backend / episode / SQLite all price through this layer so
there is no second, conflicting rate table.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.backend.rates import (
    RATE_SOURCE,
    RATE_SOURCE_VERIFIED_ON,
    RATE_VERSION,
    RATES,
    estimated_cost as _rate_estimated_cost,
    rate_metadata,
)

KNOWN = "KNOWN"
UNKNOWN_USAGE = "UNKNOWN_USAGE"
UNKNOWN_RATE = "UNKNOWN_RATE"
TRANSPORT_UNCERTAIN = "TRANSPORT_UNCERTAIN"


class CostStatus:
    def __init__(self, status: str, cost: float, model: str = "", detail: str = "") -> None:
        self.status = status
        self.cost = float(cost)
        self.model = model
        self.detail = detail

    @property
    def is_known(self) -> bool:
        return self.status == KNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "estimated_cost_usd": self.cost,
            "model": self.model,
            "rate_version": RATE_VERSION,
            "detail": self.detail,
        }


def estimate_cost(
    model: str,
    tokens_in: Optional[int],
    tokens_out: Optional[int],
) -> CostStatus:
    """Never silently zero unknowns. Unknown model → UNKNOWN_RATE (no cheap map)."""
    if tokens_in is None or tokens_out is None:
        return CostStatus(UNKNOWN_USAGE, 0.0, model, "missing usage fields")
    try:
        tin, tout = int(tokens_in), int(tokens_out)
    except Exception as e:
        return CostStatus(UNKNOWN_USAGE, 0.0, model, f"bad usage: {e}")
    if model not in RATES:
        return CostStatus(UNKNOWN_RATE, 0.0, model, f"no rate for {model}")
    try:
        cost = _rate_estimated_cost(model, tin, tout)
        return CostStatus(KNOWN, cost, model, "")
    except Exception as e:
        return CostStatus(UNKNOWN_RATE, 0.0, model, f"rate error: {e}")


def backend_estimated_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Same formula as transport (consistency for reconciliation)."""
    cs = estimate_cost(model, tokens_in, tokens_out)
    if not cs.is_known:
        raise ValueError(f"cannot price model {model!r}: {cs.status}")
    return cs.cost


__all__ = [
    "KNOWN",
    "UNKNOWN_USAGE",
    "UNKNOWN_RATE",
    "TRANSPORT_UNCERTAIN",
    "RATE_VERSION",
    "RATE_SOURCE",
    "RATE_SOURCE_VERIFIED_ON",
    "CostStatus",
    "estimate_cost",
    "backend_estimated_cost",
    "rate_metadata",
]
