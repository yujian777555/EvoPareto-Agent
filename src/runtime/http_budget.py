"""SQLite-backed physical HTTP budget (Phase5-R3-R5-R1 Task A)."""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


class BudgetExceeded(RuntimeError):
    pass


class BillingBlocked(RuntimeError):
    pass


class BudgetDB:
    """Cross-process atomic budget ledger."""

    def __init__(self, path: str | Path, max_calls: int = 100, max_cost_usd: float = 1.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_calls = max_calls
        self.max_cost_usd = max_cost_usd
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS budget (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                reserved_calls INTEGER NOT NULL DEFAULT 0,
                reserved_cost REAL NOT NULL DEFAULT 0,
                spent_cost REAL NOT NULL DEFAULT 0,
                logical_ok INTEGER NOT NULL DEFAULT 0,
                logical_failed INTEGER NOT NULL DEFAULT 0,
                physical_attempts INTEGER NOT NULL DEFAULT 0,
                retries INTEGER NOT NULL DEFAULT 0,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO budget (id) VALUES (1)"
        )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _row(self) -> sqlite3.Row:
        return self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            r = self._row()
            return {
                "reserved_calls": r["reserved_calls"],
                "reserved_cost_usd": r["reserved_cost"],
                "spent_cost_usd": r["spent_cost"],
                "logical_ok": r["logical_ok"],
                "logical_failed": r["logical_failed"],
                "physical_attempts": r["physical_attempts"],
                "retries": r["retries"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "max_calls": self.max_calls,
                "max_cost_usd": self.max_cost_usd,
            }

    def reserve(self, est_cost: float, is_retry: bool = False) -> int:
        """Atomically reserve one physical attempt. Returns ticket id."""
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                r = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
                started = r["logical_ok"] + r["logical_failed"] + r["reserved_calls"]
                if started + r["physical_attempts"] * 0 + r["reserved_calls"] >= self.max_calls and (
                    r["logical_ok"] + r["logical_failed"] + r["reserved_calls"] >= self.max_calls
                ):
                    # physical + logical share the same cap
                    if r["physical_attempts"] >= self.max_calls or (
                        r["logical_ok"] + r["logical_failed"] + r["reserved_calls"]
                        >= self.max_calls
                    ):
                        conn.execute("ROLLBACK")
                        raise BudgetExceeded("max_calls reached")
                if r["spent_cost"] + r["reserved_cost"] + est_cost > self.max_cost_usd:
                    conn.execute("ROLLBACK")
                    raise BudgetExceeded("max_cost reached")
                conn.execute(
                    "UPDATE budget SET reserved_calls=reserved_calls+1, "
                    "reserved_cost=reserved_cost+?, physical_attempts=physical_attempts+1, "
                    "retries=retries+? WHERE id=1",
                    (float(est_cost), 1 if is_retry else 0),
                )
                conn.execute("COMMIT")
                return r["physical_attempts"] + 1
            except BudgetExceeded:
                raise
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def settle(self, est_cost: float, *, success: bool, actual_in: int = 0,
               actual_out: int = 0, actual_cost: float = 0.0) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE budget SET reserved_calls=MAX(0, reserved_calls-1), "
                    "reserved_cost=MAX(0, reserved_cost-?), spent_cost=spent_cost+?, "
                    "logical_ok=logical_ok+?, logical_failed=logical_failed+?, "
                    "tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=1",
                    (
                        float(est_cost),
                        max(0.0, float(actual_cost)),
                        1 if success else 0,
                        0 if success else 1,
                        int(actual_in),
                        int(actual_out),
                    ),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise


class PhysicalBudgetGate:
    """Transport-level pre-send approval. HTTP must not send if denied."""

    def __init__(self, db: BudgetDB, est_cost_per_request: float = 0.0005) -> None:
        self.db = db
        self.est_cost = est_cost_per_request
        self._local = threading.local()
        self._active_ticket: Dict[int, float] = {}
        self._tlock = threading.Lock()

    def approve(self, *, is_retry: bool = False) -> None:
        """Called before EVERY physical send. Raises if budget denied."""
        est = self.db.reserve(self.est_cost, is_retry=is_retry)
        with self._tlock:
            self._active_ticket[id(threading.current_thread())] = est

    def release(self, *, success: bool, actual_cost: float = 0.0,
                actual_in: int = 0, actual_out: int = 0) -> None:
        with self._tlock:
            est = self._active_ticket.pop(id(threading.current_thread()), self.est_cost)
        self.db.settle(est, success=success, actual_cost=actual_cost,
                       actual_in=actual_in, actual_out=actual_out)

    def force_release_all(self) -> None:
        with self._tlock:
            leftovers = list(self._active_ticket.items())
            self._active_ticket.clear()
        for _, est in leftovers:
            self.db.settle(est, success=False)


_GLOBAL_GATE: Optional[PhysicalBudgetGate] = None
_GLOBAL_LOCK = threading.Lock()


def install_global_gate(gate: PhysicalBudgetGate) -> None:
    global _GLOBAL_GATE
    with _GLOBAL_LOCK:
        _GLOBAL_GATE = gate


def get_global_gate() -> Optional[PhysicalBudgetGate]:
    with _GLOBAL_LOCK:
        return _GLOBAL_GATE


def pre_send_approval(*, is_retry: bool = False) -> None:
    """http_client hook: approve or raise BEFORE any network I/O."""
    gate = _GLOBAL_GATE
    if gate is None:
        return
    gate.approve(is_retry=is_retry)
