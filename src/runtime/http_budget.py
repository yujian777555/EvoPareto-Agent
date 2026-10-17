"""Physical HTTP budget with ticket lifecycle (Phase5-R3-R5-R2 P0-A).

Fail-closed when formal mode requires a gate and none is installed.
Every physical attempt has a unique ticket; settle exactly once.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional


class BudgetExceeded(RuntimeError):
    pass


class BillingBlocked(RuntimeError):
    pass


class GateRequired(RuntimeError):
    """Formal real-API mode without an installed budget gate."""


class UnknownTicket(RuntimeError):
    pass


class BudgetDB:
    """SQLite WAL ledger. physical_attempts is the hard HTTP cap."""

    def __init__(self, path: str | Path, max_physical: int = 100, max_cost_usd: float = 1.0) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_physical = max_physical
        self.max_cost_usd = max_cost_usd
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budget (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    max_physical INTEGER NOT NULL,
                    max_cost_usd REAL NOT NULL,
                    physical_attempts INTEGER NOT NULL DEFAULT 0,
                    reserved_tickets INTEGER NOT NULL DEFAULT 0,
                    settled_ok INTEGER NOT NULL DEFAULT 0,
                    settled_failed INTEGER NOT NULL DEFAULT 0,
                    reserved_cost REAL NOT NULL DEFAULT 0,
                    spent_cost REAL NOT NULL DEFAULT 0,
                    tokens_in INTEGER NOT NULL DEFAULT 0,
                    tokens_out INTEGER NOT NULL DEFAULT 0,
                    retries INTEGER NOT NULL DEFAULT 0,
                    max_tokens_in INTEGER NOT NULL DEFAULT 2000000,
                    max_tokens_out INTEGER NOT NULL DEFAULT 200000
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY,
                    est_cost REAL NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    reserved_tokens_in INTEGER NOT NULL DEFAULT 0,
                    reserved_tokens_out INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            row = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO budget (id, max_physical, max_cost_usd) VALUES (1, ?, ?)",
                    (self.max_physical, self.max_cost_usd),
                )
            else:
                # Do not silently raise caps.
                if int(row["max_physical"]) < self.max_physical:
                    self.max_physical = int(row["max_physical"])
                if float(row["max_cost_usd"]) < self.max_cost_usd:
                    self.max_cost_usd = float(row["max_cost_usd"])
                # NOTE: do NOT abandon open tickets on every process start —
                # that would free another live process's reservation.
                # Crash recovery is explicit via recover_stale().
            self._conn.commit()

    def recover_stale(self, older_than_seconds: float = 3600.0) -> int:
        """Expire only tickets proven stale by age (crash recovery).

        Does NOT touch fresh open tickets belonging to live processes.
        """
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                rows = conn.execute(
                    "SELECT id FROM tickets WHERE status='open' "
                    "AND CAST(created_at AS REAL) <= strftime('%s','now') - ?",
                    (int(older_than_seconds),),
                ).fetchall()
                stale_ids = [r["id"] for r in rows]
                if stale_ids:
                    est_sum = conn.execute(
                        "SELECT COALESCE(SUM(est_cost),0) AS s FROM tickets WHERE id IN ({seq})".format(
                            seq=",".join("?" * len(stale_ids))
                        ),
                        tuple(stale_ids),
                    ).fetchone()["s"]
                    conn.execute(
                        "UPDATE budget SET physical_attempts = physical_attempts + ?, "
                        "reserved_tickets=MAX(0, reserved_tickets-?), "
                        "reserved_cost=MAX(0, reserved_cost - ?) WHERE id=1",
                        (len(stale_ids), len(stale_ids), float(est_sum)),
                    )
                    conn.execute(
                        "UPDATE tickets SET status='abandoned' WHERE id IN ({seq})".format(
                            seq=",".join("?" * len(stale_ids))
                        ),
                        tuple(stale_ids),
                    )
                conn.execute("COMMIT")
                return len(stale_ids)
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            r = self._conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
            open_n = self._conn.execute(
                "SELECT COUNT(*) AS c FROM tickets WHERE status='open'"
            ).fetchone()["c"]
            return {
                "physical_attempts": r["physical_attempts"],
                "max_physical": r["max_physical"],
                "reserved_tickets": r["reserved_tickets"],
                "open_tickets": open_n,
                "settled_ok": r["settled_ok"],
                "settled_failed": r["settled_failed"],
                "reserved_cost_usd": r["reserved_cost"],
                "spent_cost_usd": r["spent_cost"],
                "tokens_in": r["tokens_in"],
                "tokens_out": r["tokens_out"],
                "retries": r["retries"],
                "max_cost_usd": r["max_cost_usd"],
            }

    def is_billing_blocked(self) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='billing_blocked'"
            ).fetchone()
            return bool(row and row["value"] == "1")

    def billing_block_reason(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key='billing_block_reason'"
            ).fetchone()
            return str(row["value"]) if row else ""

    @staticmethod
    def _rollback_quiet(conn: sqlite3.Connection) -> None:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass

    def mark_billing_blocked(self, reason: str, ticket_id: str = "") -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('billing_blocked','1') "
                    "ON CONFLICT(key) DO UPDATE SET value='1'"
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('billing_block_reason', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(reason),),
                )
                if ticket_id:
                    conn.execute(
                        "INSERT INTO meta (key, value) VALUES ('unknown_cost_ticket_id', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (str(ticket_id),),
                    )
                conn.execute("COMMIT")
            except Exception:
                self._rollback_quiet(conn)
                raise

    def acquire_ticket(
        self,
        est_cost: float,
        *,
        is_retry: bool = False,
        res_tokens_in: int = 0,
        res_tokens_out: int = 0,
    ) -> str:
        """Atomic pre-send reservation. Returns ticket id. Raises if denied.

        Billing-block check runs INSIDE BEGIN IMMEDIATE so a block committed
        by another process is observed before any new reservation.
        Cumulative token quotas are checked and reserved atomically.
        """
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT value FROM meta WHERE key='billing_blocked'"
                ).fetchone()
                if row and row["value"] == "1":
                    reason = conn.execute(
                        "SELECT value FROM meta WHERE key='billing_block_reason'"
                    ).fetchone()
                    raise BillingBlocked(
                        str(reason["value"]) if reason else "billing blocked"
                    )
                r = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
                open_n = conn.execute(
                    "SELECT COUNT(*) AS c FROM tickets WHERE status='open'"
                ).fetchone()["c"]
                if r["physical_attempts"] + open_n >= r["max_physical"]:
                    raise BudgetExceeded("max physical HTTP attempts reached")
                # cumulative token quotas (hard cap)
                if int(r["tokens_in"]) + int(res_tokens_in) > int(r["max_tokens_in"]):
                    raise BudgetExceeded("max cumulative input tokens reached")
                if int(r["tokens_out"]) + int(res_tokens_out) > int(r["max_tokens_out"]):
                    raise BudgetExceeded("max cumulative output tokens reached")
                if r["spent_cost"] + r["reserved_cost"] + float(est_cost) > r["max_cost_usd"]:
                    raise BudgetExceeded("max cost reached")
                tid = uuid.uuid4().hex
                conn.execute(
                    "INSERT INTO tickets (id, est_cost, status, created_at, "
                    "reserved_tokens_in, reserved_tokens_out) "
                    "VALUES (?, ?, 'open', strftime('%s','now'), ?, ?)",
                    (tid, float(est_cost), int(res_tokens_in), int(res_tokens_out)),
                )
                conn.execute(
                    "UPDATE budget SET reserved_tickets=reserved_tickets+1, "
                    "reserved_cost=reserved_cost+?, retries=retries+?, "
                    "tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=1",
                    (float(est_cost), 1 if is_retry else 0, int(res_tokens_in), int(res_tokens_out)),
                )
                conn.execute("COMMIT")
                return tid
            except Exception:
                self._rollback_quiet(conn)
                raise

    def settle(
        self,
        ticket: str,
        *,
        success: bool,
        actual_cost: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                t = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
                if t is None:
                    raise UnknownTicket(ticket)
                if t["status"] != "open":
                    raise RuntimeError(f"ticket already settled: {ticket}")
                est = float(t["est_cost"])
                conn.execute(
                    "UPDATE tickets SET status='settled' WHERE id=?", (ticket,)
                )
                conn.execute(
                    "UPDATE budget SET physical_attempts=physical_attempts+1, "
                    "reserved_tickets=MAX(0,reserved_tickets-1), "
                    "reserved_cost=MAX(0,reserved_cost-?), spent_cost=spent_cost+?, "
                    "settled_ok=settled_ok+?, settled_failed=settled_failed+? "
                    "WHERE id=1",
                    (
                        est,
                        max(0.0, float(actual_cost)),
                        1 if success else 0,
                        0 if success else 1,
                    ),
                )
                res_in = int(t["reserved_tokens_in"] or 0)
                res_out = int(t["reserved_tokens_out"] or 0)
                extra_in = max(0, int(tokens_in) - res_in)
                extra_out = max(0, int(tokens_out) - res_out)
                conn.execute(
                    "UPDATE budget SET tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=1",
                    (extra_in, extra_out),
                )
                conn.execute(
                    "UPDATE tickets SET reserved_tokens_in=0, reserved_tokens_out=0 WHERE id=?",
                    (ticket,),
                )
                conn.execute("COMMIT")
            except Exception:
                self._rollback_quiet(conn)
                raise

    def settle_unknown_and_block(
        self,
        ticket: str,
        *,
        reason: str,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        """One atomic transaction: settle ticket + persistent billing block.

        The physical attempt is recorded and billing_blocked=1 is written in
        the SAME BEGIN IMMEDIATE transaction. Commit failure propagates.
        """
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                t = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket,)).fetchone()
                if t is None:
                    raise UnknownTicket(ticket)
                if t["status"] != "open":
                    raise RuntimeError(f"ticket already settled: {ticket}")
                est = float(t["est_cost"])
                conn.execute("UPDATE tickets SET status='settled' WHERE id=?", (ticket,))
                conn.execute(
                    "UPDATE budget SET physical_attempts=physical_attempts+1, "
                    "reserved_tickets=MAX(0,reserved_tickets-1), "
                    "reserved_cost=MAX(0,reserved_cost-?), "
                    "settled_failed=settled_failed+1, "
                    "tokens_in=tokens_in+?, tokens_out=tokens_out+? WHERE id=1",
                    (est, int(tokens_in), int(tokens_out)),
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('billing_blocked','1') "
                    "ON CONFLICT(key) DO UPDATE SET value='1'"
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('billing_block_reason', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(reason),),
                )
                conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('unknown_cost_ticket_id', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(ticket),),
                )
                conn.execute("COMMIT")
            except Exception:
                self._rollback_quiet(conn)
                raise


class PhysicalBudgetGate:
    """Per-attempt ticket gate. approve() then network then settle(ticket)."""

    def __init__(self, db: BudgetDB, est_cost_per_request: float = 0.0005) -> None:
        self.db = db
        self.est_cost = est_cost_per_request

    def approve(
        self,
        *,
        is_retry: bool = False,
        res_tokens_in: int = 0,
        res_tokens_out: int = 0,
    ) -> str:
        return self.db.acquire_ticket(
            self.est_cost,
            is_retry=is_retry,
            res_tokens_in=res_tokens_in,
            res_tokens_out=res_tokens_out,
        )

    def settle(
        self,
        ticket: str,
        *,
        success: bool,
        actual_cost: float = 0.0,
        tokens_in: int = 0,
        tokens_out: int = 0,
    ) -> None:
        self.db.settle(
            ticket,
            success=success,
            actual_cost=actual_cost,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )


_GATE: Optional[PhysicalBudgetGate] = None
_LOCK = threading.Lock()
_STRICT = False  # formal real-API mode: require gate


def install_global_gate(gate: PhysicalBudgetGate, *, strict: bool = False) -> None:
    global _GATE, _STRICT
    with _LOCK:
        _GATE = gate
        _STRICT = bool(strict)


def get_global_gate() -> Optional[PhysicalBudgetGate]:
    with _LOCK:
        return _GATE


def set_strict_mode(flag: bool) -> None:
    global _STRICT
    with _LOCK:
        _STRICT = bool(flag)


def pre_send_ticket(
    *,
    is_retry: bool = False,
    res_tokens_in: int = 0,
    res_tokens_out: int = 0,
) -> str:
    """Must be called before every physical send.

    - strict mode + no gate => GateRequired (no send)
    - gate error => propagate (no send)
    """
    with _LOCK:
        gate = _GATE
        strict = _STRICT
    if gate is None:
        if strict:
            raise GateRequired("strict mode: physical HTTP requires installed Budget gate")
        return ""  # offline / non-research path
    return gate.approve(
        is_retry=is_retry,
        res_tokens_in=res_tokens_in,
        res_tokens_out=res_tokens_out,
    )


def settle_ticket(ticket: str, *, success: bool, **kwargs: Any) -> None:
    with _LOCK:
        gate = _GATE
    if gate is None or not ticket:
        return
    gate.settle(ticket, success=success, **kwargs)
