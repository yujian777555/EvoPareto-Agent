"""Global API budget with correct reserve settlement (Phase5-R3-R5 Stage A).

- reserved_cost is released in _settle (fixes leak at 9ebddc6)
- physical HTTP attempts counted via request hook
- 402/401/403 fail-fast
- optional persistent ledger for cross-process budgets
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class BudgetExceeded(RuntimeError):
    pass


class BillingBlocked(RuntimeError):
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
    physical_http_attempts: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "estimated_in": self.estimated_in,
            "estimated_out": self.estimated_out,
            "actual_in": self.actual_in,
            "actual_out": self.actual_out,
            "requests_ok": self.requests_ok,
            "requests_failed": self.requests_failed,
            "retries": self.retries,
            "physical_http_attempts": self.physical_http_attempts,
            "actual_total_tokens": self.actual_in + self.actual_out,
            "estimated_total_tokens": self.estimated_in + self.estimated_out,
        }


class APICallGate:
    """Hard budget over logical LLM calls AND physical HTTP attempts."""

    def __init__(
        self,
        backend_generate: Callable[..., Any],
        *,
        max_calls: int = 100,
        max_cost_usd: float = 1.0,
        max_retries: int = 1,
        cost_per_1k_in: float = 0.0001,
        cost_per_1k_out: float = 0.0002,
        ledger_path: Optional[str] = None,
    ) -> None:
        self.backend_generate = backend_generate
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self.max_retries = max_retries
        self.cost_per_1k_in = cost_per_1k_in
        self.cost_per_1k_out = cost_per_1k_out
        self._lock = threading.RLock()
        self.ledger = TokenLedger()
        self.reserved_calls = 0
        self.spent_cost = 0.0
        self.reserved_cost = 0.0
        self._pending_cost: Dict[int, float] = {}
        self._ticket = 0
        self.ledger_path = Path(ledger_path) if ledger_path else None
        if self.ledger_path and self.ledger_path.exists():
            self._restore(self.ledger_path)

    def _restore(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.get("ledger", {}).items():
                if hasattr(self.ledger, k):
                    setattr(self.ledger, k, int(v))
            self.spent_cost = float(data.get("spent_cost", 0.0))
        except Exception:
            pass

    def persist(self) -> None:
        if not self.ledger_path:
            return
        with self._lock:
            payload = {
                "ledger": self.ledger.to_dict(),
                "spent_cost": self.spent_cost,
                "updated_at": time.time(),
            }
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _reserve(self, est_tokens: int, is_retry: bool = False) -> int:
        est_cost = (est_tokens / 1000.0) * self.cost_per_1k_in + 0.0002
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
            self._ticket += 1
            self._pending_cost[self._ticket] = est_cost
            self.ledger.estimated_in += est_tokens
            if is_retry:
                self.ledger.retries += 1
            return self._ticket

    def _settle(
        self,
        ticket: int,
        *,
        success: bool,
        actual_in: int = 0,
        actual_out: int = 0,
        actual_cost: float = 0.0,
    ) -> None:
        with self._lock:
            est = self._pending_cost.pop(ticket, 0.0)
            if self.reserved_calls > 0:
                self.reserved_calls -= 1
            self.reserved_cost = max(0.0, self.reserved_cost - est)
            self.spent_cost += max(0.0, float(actual_cost))
            if success:
                self.ledger.requests_ok += 1
                self.ledger.actual_in += int(actual_in)
                self.ledger.actual_out += int(actual_out)
            else:
                self.ledger.requests_failed += 1

    def note_physical_http(self) -> None:
        """Count one physical HTTP send (curl/urllib)."""
        with self._lock:
            self.ledger.physical_http_attempts += 1

    def physical_budget_ok(self) -> bool:
        with self._lock:
            return self.ledger.physical_http_attempts < self.max_calls

    def generate(self, prompt: str, *, budget: int = 32, **kwargs: Any):
        est = max(8, len(prompt) // 4) + max(8, int(budget) * 2)
        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            ticket = self._reserve(est, is_retry=attempt > 0)
            try:
                resp = self.backend_generate(prompt, budget=budget, **kwargs)
                ain = int(getattr(resp, "tokens_prompt", 0) or 0)
                aout = int(getattr(resp, "tokens_completion", 0) or 0)
                acost = float(getattr(resp, "cost", 0.0) or 0.0)
                self._settle(ticket, success=True, actual_in=ain, actual_out=aout, actual_cost=acost)
                self.persist()
                return resp
            except Exception as e:
                # Always release reservation; physical send may still have occurred.
                self._settle(ticket, success=False)
                self.persist()
                last_err = e
                msg = str(e)
                if "402" in msg or "Payment Required" in msg:
                    raise BillingBlocked(f"BLOCKED_BILLING: {e}") from e
                if "401" in msg or "403" in msg:
                    raise BillingBlocked(f"BLOCKED_AUTH: {e}") from e
        raise RuntimeError(f"LLM failed after retries under budget gate: {last_err}")

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            d = self.ledger.to_dict()
            d.update(
                {
                    "max_calls": self.max_calls,
                    "max_cost_usd": self.max_cost_usd,
                    "spent_cost_usd": self.spent_cost,
                    "reserved_cost_usd": self.reserved_cost,
                    "reserved_calls": self.reserved_calls,
                    "pending_reservations": len(self._pending_cost),
                }
            )
            return d

    def assert_clean_shutdown(self) -> None:
        snap = self.snapshot()
        if snap["reserved_calls"] != 0 or snap["reserved_cost_usd"] > 1e-12:
            raise AssertionError(f"reservation leak: {snap}")


# Process-global physical HTTP counter (thread-safe).
_PHYS_LOCK = threading.Lock()
_PHYS_COUNT = 0


def bump_physical_http() -> int:
    global _PHYS_COUNT
    with _PHYS_LOCK:
        _PHYS_COUNT += 1
        return _PHYS_COUNT


def physical_http_count() -> int:
    with _PHYS_LOCK:
        return _PHYS_COUNT


def reset_physical_http() -> None:
    global _PHYS_COUNT
    with _PHYS_LOCK:
        _PHYS_COUNT = 0
