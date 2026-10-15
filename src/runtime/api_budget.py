"""Hard API budget gate (Phase5-R3-R4 Task1).

Pre-request atomic reserve; retries consume budget; conservative cost
reservation; lost responses still count as spent requests.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class TokenLedger:
    estimated_in: int = 0
    estimated_out: int = 0
    actual_in: int = 0
    actual_out: int = 0
    requests_ok: int = 0
    requests_failed: int = 0
    retries: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "estimated_in": self.estimated_in,
            "estimated_out": self.estimated_out,
            "actual_in": self.actual_in,
            "actual_out": self.actual_out,
            "requests_ok": self.requests_ok,
            "requests_failed": self.requests_failed,
            "retries": self.retries,
            "actual_total_tokens": self.actual_in + self.actual_out,
            "estimated_total_tokens": self.estimated_in + self.estimated_out,
        }


class APICallGate:
    """Wraps any LLM generate with hard budget enforcement."""

    def __init__(
        self,
        backend_generate: Callable[..., Any],
        *,
        max_calls: int = 100,
        max_cost_usd: float = 1.0,
        max_retries: int = 1,
        cost_per_1k_in: float = 0.0001,
        cost_per_1k_out: float = 0.0002,
    ) -> None:
        self.backend_generate = backend_generate
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self.max_retries = max_retries
        self.cost_per_1k_in = cost_per_1k_in
        self.cost_per_1k_out = cost_per_1k_out
        self._lock = threading.Lock()
        self.ledger = TokenLedger()
        self.reserved_calls = 0
        self.spent_cost = 0.0
        self.reserved_cost = 0.0

    def _reserve(self, est_tokens: int, is_retry: bool = False) -> None:
        est_cost = (est_tokens / 1000.0) * self.cost_per_1k_in
        with self._lock:
            total_started = (
                self.ledger.requests_ok + self.ledger.requests_failed + self.reserved_calls
            )
            if total_started >= self.max_calls:
                raise BudgetExceeded(f"max_calls {self.max_calls} reached")
            if self.spent_cost + self.reserved_cost + est_cost > self.max_cost_usd:
                raise BudgetExceeded(f"max_cost {self.max_cost_usd} reached")
            self.reserved_calls += 1
            self.reserved_cost += est_cost
            self.ledger.estimated_in += est_tokens
            if is_retry:
                self.ledger.retries += 1

    def _settle(self, *, success: bool, actual_in: int, actual_out: int, actual_cost: float) -> None:
        with self._lock:
            if self.reserved_calls > 0:
                self.reserved_calls -= 1
            self.spent_cost += max(0.0, float(actual_cost))
            if success:
                self.ledger.requests_ok += 1
                self.ledger.actual_in += int(actual_in)
                self.ledger.actual_out += int(actual_out)
            else:
                self.ledger.requests_failed += 1

    def generate(self, prompt: str, *, budget: int = 32, **kwargs: Any):
        """Reserve before each attempt (retries included). 402 fails fast."""
        est = max(8, len(prompt) // 4) + max(8, int(budget) * 2)
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._reserve(est, is_retry=attempt > 0)
            try:
                resp = self.backend_generate(prompt, budget=budget, **kwargs)
                ain = int(getattr(resp, "tokens_prompt", 0) or 0)
                aout = int(getattr(resp, "tokens_completion", 0) or 0)
                acost = float(getattr(resp, "cost", 0.0) or 0.0)
                self._settle(success=True, actual_in=ain, actual_out=aout, actual_cost=acost)
                return resp
            except Exception as e:
                self._settle(success=False, actual_in=0, actual_out=0, actual_cost=0.0)
                last_err = e
                msg = str(e)
                if "402" in msg or "Payment Required" in msg:
                    # Billing: never retry the same charge error.
                    raise RuntimeError(f"BLOCKED_BILLING: {e}") from e
                if "401" in msg or "403" in msg:
                    raise RuntimeError(f"BLOCKED_AUTH: {e}") from e
        raise RuntimeError(f"LLM failed after retries under budget gate: {last_err}")

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            d = self.ledger.to_dict()
            d.update({
                "max_calls": self.max_calls,
                "max_cost_usd": self.max_cost_usd,
                "spent_cost_usd": self.spent_cost,
                "reserved_cost_usd": self.reserved_cost,
                "reserved_calls": self.reserved_calls,
            })
            return d
