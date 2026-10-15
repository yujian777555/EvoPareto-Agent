"""Thread-safe request/episode budget manager (Phase5-R3-R2 Stage A2).

Atomic reserve → settle (success/fail). Enforces:
  - max API calls
  - max USD cost
  - max episode steps

Reserve BEFORE the request; settle AFTER completion.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetManager:
    max_calls: int = 5000
    max_cost_usd: float = 20.0
    max_episode_steps: int = 10000

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    reserved_calls: int = 0
    completed_calls: int = 0
    failed_calls: int = 0
    cached_hits: int = 0
    retries: int = 0
    reserved_cost: float = 0.0
    settled_cost: float = 0.0
    episode_steps: int = 0

    # --- call budget ---
    def reserve_call(self, estimated_cost: float = 0.0) -> int:
        """Atomically reserve one API call. Returns reservation id."""
        with self._lock:
            if self.reserved_calls + self.completed_calls + self.failed_calls >= self.max_calls:
                raise BudgetExceeded("max API calls reached")
            if self.settled_cost + self.reserved_cost + estimated_cost > self.max_cost_usd:
                raise BudgetExceeded("max cost reached")
            self.reserved_calls += 1
            self.reserved_cost += float(estimated_cost)
            return self.reserved_calls + self.completed_calls + self.failed_calls

    def settle_call(self, *, success: bool, actual_cost: float = 0.0, cached: bool = False,
                    retried: bool = False) -> None:
        with self._lock:
            if self.reserved_calls > 0:
                self.reserved_calls -= 1
            if retried:
                self.retries += 1
            if cached:
                self.cached_hits += 1
            if success:
                self.completed_calls += 1
            else:
                self.failed_calls += 1
            self.settled_cost += float(actual_cost)

    # --- episode steps ---
    def charge_steps(self, n: int = 1) -> None:
        with self._lock:
            if self.episode_steps + int(n) > self.max_episode_steps:
                raise BudgetExceeded("max episode steps reached")
            self.episode_steps += int(n)

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {
                "reserved_calls": self.reserved_calls,
                "completed_calls": self.completed_calls,
                "failed_calls": self.failed_calls,
                "cached_hits": self.cached_hits,
                "retries": self.retries,
                "reserved_cost": self.reserved_cost,
                "settled_cost": self.settled_cost,
                "episode_steps": self.episode_steps,
                "max_calls": self.max_calls,
                "max_cost_usd": self.max_cost_usd,
                "max_episode_steps": self.max_episode_steps,
            }

    @property
    def total_started_calls(self) -> int:
        with self._lock:
            return self.reserved_calls + self.completed_calls + self.failed_calls
