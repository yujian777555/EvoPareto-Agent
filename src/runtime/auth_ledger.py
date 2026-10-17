"""Persistent authorization ledger (Level 3-R2 Task A/C).

Design goals (normal-experiment threat model, not full-FS attacker):
  * Deleting the working DB must NOT restore consumed quota.
  * Restart / run-id rotation / DB-path change must NOT restore quota.
  * A missing or corrupt trusted authorization record FAILS CLOSED.
  * New authorization requires an explicit create_authorization() call.
  * Request lifecycle is a strict state machine:
        RESERVED -> SETTLED_ACTUAL
        RESERVED -> SETTLED_UNKNOWN_BLOCKED
    No transition out of a terminal state; no silent repair to success.

The trusted authorization record is a checksummed JSON file kept at a fixed
workspace path. The working SQLite DB is a per-session detail store that can be
deleted; consumption is rehydrated from the record, never from zero.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORD_PATH = ROOT / "results" / "level3_live_calibration" / "authorization_record.json"

STATE_RESERVED = "RESERVED"
STATE_SETTLED_ACTUAL = "SETTLED_ACTUAL"
STATE_SETTLED_UNKNOWN_BLOCKED = "SETTLED_UNKNOWN_BLOCKED"
TERMINAL_STATES = (STATE_SETTLED_ACTUAL, STATE_SETTLED_UNKNOWN_BLOCKED)


class AuthorizationError(RuntimeError):
    pass


class AuthorizationMissing(AuthorizationError):
    pass


class AuthorizationIntegrityError(AuthorizationError):
    pass


class BudgetExceeded(AuthorizationError):
    pass


class DuplicateSettlement(AuthorizationError):
    pass


class DuplicatePhysicalRequest(AuthorizationError):
    pass


class UnknownBillingBlocked(AuthorizationError):
    pass


def _canonical(body: Dict[str, Any]) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity_of(body: Dict[str, Any], key: str) -> str:
    payload = dict(body)
    payload.pop("integrity", None)
    return hashlib.sha256((key + "|" + _canonical(payload)).encode("utf-8")).hexdigest()


class AuthorizationRecord:
    """Trusted, checksummed cumulative-usage record. Survives working-DB deletion."""

    def __init__(self, path: Path, body: Dict[str, Any], secret_key: str) -> None:
        self.path = Path(path)
        self._body = body
        self._key = secret_key
        self._lock = threading.RLock()

    # ---------- factory ----------
    @staticmethod
    def create(path: Path, *, auth_id: str, caps: Dict[str, int], secret_key: str) -> "AuthorizationRecord":
        """Explicit authorization creation. Only path that mints a new quota."""
        path = Path(path)
        if path.exists():
            raise AuthorizationError(
                f"AUTHORIZATION_ALREADY_EXISTS:{path} — use open_existing(); "
                "new quota requires an explicit re-authorization procedure"
            )
        body = {
            "auth_id": auth_id,
            "created_at": time.time(),
            "caps": {
                "max_physical": int(caps["max_physical"]),
                "max_cost_usd": float(caps["max_cost_usd"]),
                "max_total_in": int(caps["max_total_in"]),
                "max_total_out": int(caps["max_total_out"]),
            },
            "consumed": {
                "physical_attempts": 0,
                "spent_cost_usd": 0.0,
                "actual_tokens_in": 0,
                "actual_tokens_out": 0,
                "reserved_tokens_in": 0,
                "reserved_tokens_out": 0,
                "outstanding_reserved_cost_usd": 0.0,
                "unknown_usage_count": 0,
            },
            "blocked": False,
            "block_reason": None,
            "history_tail": [],
        }
        body["integrity"] = _integrity_of(body, secret_key)
        rec = AuthorizationRecord(path, body, secret_key)
        rec._persist()
        return rec

    @staticmethod
    def open_existing(path: Path, *, secret_key: str) -> "AuthorizationRecord":
        """Load + verify. Missing/corrupt record FAILS CLOSED (never re-mints)."""
        path = Path(path)
        if not path.exists():
            raise AuthorizationMissing(
                f"AUTHORIZATION_RECORD_MISSING:{path} — fail-closed, no new quota"
            )
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            raise AuthorizationIntegrityError(f"AUTHORIZATION_UNREADABLE:{e}") from e
        stored = body.get("integrity")
        expect = _integrity_of(body, secret_key)
        if not stored or stored != expect:
            raise AuthorizationIntegrityError("AUTHORIZATION_INTEGRITY_MISMATCH")
        return AuthorizationRecord(path, body, secret_key)

    # ---------- accessors ----------
    @property
    def auth_id(self) -> str:
        return str(self._body["auth_id"])

    @property
    def caps(self) -> Dict[str, Any]:
        return dict(self._body["caps"])

    @property
    def consumed(self) -> Dict[str, Any]:
        return dict(self._body["consumed"])

    def remaining_physical(self) -> int:
        return int(self._body["caps"]["max_physical"]) - int(self._body["consumed"]["physical_attempts"])

    def _persist(self) -> None:
        # write-then-rename for atomicity against partial writes
        self._body["integrity"] = _integrity_of(self._body, self._key)
        tmp = self.path.with_suffix(self.path.suffix + f".tmp{os.getpid()}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(self._body, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)

    def update(self, mutator) -> None:
        with self._lock:
            mutator(self._body)
            self._persist()


class AuthBudgetLedger:
    """Unified atomic budget entry: reservation + settlement state machine."""

    def __init__(self, working_db: Path, record: AuthorizationRecord) -> None:
        self.working_db = Path(working_db)
        self.record = record
        self._lock = threading.RLock()
        self.working_db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.working_db), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        # rehydrate: if record says we consumed more than this DB shows, trust record
        self._rehydrate_from_record()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requests (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    physical_request_id TEXT NOT NULL UNIQUE,
                    auth_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    logical_request_id TEXT NOT NULL,
                    request_phase TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    state TEXT NOT NULL,
                    reserved_tokens_in INTEGER NOT NULL,
                    reserved_tokens_out INTEGER NOT NULL,
                    reserved_cost_usd REAL NOT NULL,
                    actual_tokens_in INTEGER,
                    actual_tokens_out INTEGER,
                    observed_cost_usd REAL,
                    http_status INTEGER,
                    model_returned TEXT,
                    finish_reason TEXT,
                    error_kind TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            self._conn.commit()

    def _rehydrate_from_record(self) -> None:
        """Working DB deletion must not restore quota: record is source of truth."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS c, COALESCE(SUM(reserved_cost_usd),0) AS r FROM requests"
            ).fetchone()
            n_local = int(row["c"])
            n_record = int(self.record.consumed["physical_attempts"])
            if n_record > n_local:
                # insert placeholder rows so local counts match the trusted record
                for i in range(n_local, n_record):
                    self._conn.execute(
                        "INSERT OR IGNORE INTO requests (physical_request_id, auth_id, run_id, "
                        "logical_request_id, request_phase, prompt_sha256, state, "
                        "reserved_tokens_in, reserved_tokens_out, reserved_cost_usd, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (f"rehydrated-{i}-{uuid.uuid4().hex[:8]}", self.record.auth_id,
                         "rehydrated", f"rehy-{i}", "rehydrated", "rehydrated",
                         STATE_SETTLED_ACTUAL, 0, 0, 0.0, time.time()),
                    )
                self._conn.commit()

    # ---------------- request lifecycle ----------------
    def reserve(
        self,
        *,
        run_id: str,
        logical_id: str,
        physical_id: str,
        phase: str,
        prompt_sha: str,
        res_in: int,
        res_out: int,
        res_cost: float,
    ) -> None:
        if not physical_id or len(physical_id) < 8:
            raise AuthorizationError("PHYSICAL_ID_INVALID")
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                # duplicate physical id?
                dup = conn.execute(
                    "SELECT state FROM requests WHERE physical_request_id=?", (physical_id,)
                ).fetchone()
                if dup is not None:
                    raise DuplicatePhysicalRequest(physical_id)

                consumed = self.record.consumed
                caps = self.record.caps
                if self.record._body.get("blocked"):
                    raise UnknownBillingBlocked(str(self.record._body.get("block_reason")))

                new_attempts = int(consumed["physical_attempts"]) + 1
                if new_attempts > int(caps["max_physical"]):
                    raise BudgetExceeded("MAX_PHYSICAL_EXCEEDED")
                outstanding = float(consumed.get("outstanding_reserved_cost_usd") or 0.0)
                if float(consumed["spent_cost_usd"]) + outstanding + float(res_cost) > float(caps["max_cost_usd"]):
                    raise BudgetExceeded("MAX_COST_EXCEEDED")
                if int(consumed["actual_tokens_in"]) + int(consumed.get("reserved_tokens_in") or 0) + int(res_in) > int(caps["max_total_in"]):
                    raise BudgetExceeded("MAX_TOTAL_INPUT_TOKENS_EXCEEDED")
                if int(consumed["actual_tokens_out"]) + int(consumed.get("reserved_tokens_out") or 0) + int(res_out) > int(caps["max_total_out"]):
                    raise BudgetExceeded("MAX_TOTAL_OUTPUT_TOKENS_EXCEEDED")

                conn.execute(
                    "INSERT INTO requests (physical_request_id, auth_id, run_id, logical_request_id, "
                    "request_phase, prompt_sha256, state, reserved_tokens_in, reserved_tokens_out, "
                    "reserved_cost_usd, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (physical_id, self.record.auth_id, run_id, logical_id, phase,
                     prompt_sha, STATE_RESERVED, int(res_in), int(res_out), float(res_cost),
                     time.time()),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

            # update trusted record (outside sqlite tx; record has its own atomic write)
            def _mut(body):
                c = body["consumed"]
                c["physical_attempts"] = int(c["physical_attempts"]) + 1
                c["reserved_tokens_in"] = int(c.get("reserved_tokens_in") or 0) + int(res_in)
                c["reserved_tokens_out"] = int(c.get("reserved_tokens_out") or 0) + int(res_out)
                c["outstanding_reserved_cost_usd"] = float(c.get("outstanding_reserved_cost_usd") or 0.0) + float(res_cost)
                tail = body.setdefault("history_tail", [])
                tail.append({"kind": "RESERVED", "pid": physical_id, "cost": float(res_cost)})
                del tail[:-200]
            self.record.update(_mut)

    def settle_actual(
        self,
        *,
        physical_id: str,
        actual_in: int,
        actual_out: int,
        observed_cost: float,
        http_status: int,
        model_returned: str,
        finish_reason: str,
    ) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM requests WHERE physical_request_id=?", (physical_id,)
                ).fetchone()
                if row is None:
                    raise AuthorizationError(f"UNKNOWN_PHYSICAL_REQUEST:{physical_id}")
                if row["state"] != STATE_RESERVED:
                    raise DuplicateSettlement(
                        f"physical_request_id={physical_id} state={row['state']}"
                    )
                conn.execute(
                    "UPDATE requests SET state=?, actual_tokens_in=?, actual_tokens_out=?, "
                    "observed_cost_usd=?, http_status=?, model_returned=?, finish_reason=? "
                    "WHERE physical_request_id=?",
                    (STATE_SETTLED_ACTUAL, int(actual_in), int(actual_out),
                     float(observed_cost), int(http_status), model_returned,
                     finish_reason, physical_id),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

            reserved_cost = float(row["reserved_cost_usd"])
            reserved_in = int(row["reserved_tokens_in"])
            reserved_out = int(row["reserved_tokens_out"])

            def _mut(body):
                c = body["consumed"]
                c["outstanding_reserved_cost_usd"] = max(
                    0.0, float(c.get("outstanding_reserved_cost_usd") or 0.0) - reserved_cost
                )
                c["reserved_tokens_in"] = max(0, int(c.get("reserved_tokens_in") or 0) - reserved_in)
                c["reserved_tokens_out"] = max(0, int(c.get("reserved_tokens_out") or 0) - reserved_out)
                c["actual_tokens_in"] = int(c["actual_tokens_in"]) + int(actual_in)
                c["actual_tokens_out"] = int(c["actual_tokens_out"]) + int(actual_out)
                c["spent_cost_usd"] = float(c["spent_cost_usd"]) + float(observed_cost)
                tail = body.setdefault("history_tail", [])
                tail.append({"kind": "SETTLED_ACTUAL", "pid": physical_id, "cost": float(observed_cost)})
                del tail[:-200]
            self.record.update(_mut)

    def settle_unknown_and_block(self, *, physical_id: str, reason: str) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM requests WHERE physical_request_id=?", (physical_id,)
                ).fetchone()
                if row is None:
                    raise AuthorizationError(f"UNKNOWN_PHYSICAL_REQUEST:{physical_id}")
                if row["state"] != STATE_RESERVED:
                    raise DuplicateSettlement(
                        f"physical_request_id={physical_id} state={row['state']}"
                    )
                conn.execute(
                    "UPDATE requests SET state=?, error_kind=? WHERE physical_request_id=?",
                    (STATE_SETTLED_UNKNOWN_BLOCKED, reason, physical_id),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

            reserved_cost = float(row["reserved_cost_usd"])

            def _mut(body):
                body["blocked"] = True
                body["block_reason"] = reason
                c = body["consumed"]
                c["unknown_usage_count"] = int(c.get("unknown_usage_count") or 0) + 1
                # unknown billing: keep the reservation as consumed (conservative)
                c["outstanding_reserved_cost_usd"] = max(
                    0.0, float(c.get("outstanding_reserved_cost_usd") or 0.0) - reserved_cost
                )
                c["spent_cost_usd"] = float(c["spent_cost_usd"]) + reserved_cost
                tail = body.setdefault("history_tail", [])
                tail.append({"kind": "SETTLED_UNKNOWN_BLOCKED", "pid": physical_id, "reason": reason})
                del tail[:-200]
            self.record.update(_mut)

    # ---------------- queries ----------------
    def request_rows(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute("SELECT * FROM requests ORDER BY seq")
            return [dict(r) for r in cur.fetchall()]

    def snapshot(self) -> Dict[str, Any]:
        return {
            "auth_id": self.record.auth_id,
            "caps": self.record.caps,
            "consumed": self.record.consumed,
            "blocked": self.record._body.get("blocked"),
            "block_reason": self.record._body.get("block_reason"),
            "remaining_physical": self.record.remaining_physical(),
            "local_request_rows": len(self.request_rows()),
        }

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Unified production HTTP gate (Task B)
# ---------------------------------------------------------------------------
class UnifiedBudgetGate:
    """Single adapter used by every real HTTP entry point.

    Request -> Validate -> Identify Authorization -> Atomic Reservation
             -> Physical Send -> Read Provider Usage -> Atomic Settlement
             -> Persist Evidence.
    """

    def __init__(self, ledger: AuthBudgetLedger, *, default_max_in: int, default_max_out: int) -> None:
        self.ledger = ledger
        self.default_max_in = default_max_in
        self.default_max_out = default_max_out

    def begin_request(
        self, *, run_id: str, phase: str, prompt_sha: str,
        res_in: int, res_out: int, res_cost: float,
    ) -> str:
        logical = f"{phase}-{uuid.uuid4().hex[:8]}"
        physical = uuid.uuid4().hex
        self.ledger.reserve(
            run_id=run_id, logical_id=logical, physical_id=physical,
            phase=phase, prompt_sha=prompt_sha,
            res_in=res_in, res_out=res_out, res_cost=res_cost,
        )
        return physical

    def complete_actual(self, physical_id: str, *, actual_in: int, actual_out: int,
                        observed_cost: float, http_status: int,
                        model_returned: str, finish_reason: str) -> None:
        self.ledger.settle_actual(
            physical_id=physical_id, actual_in=actual_in, actual_out=actual_out,
            observed_cost=observed_cost, http_status=http_status,
            model_returned=model_returned, finish_reason=finish_reason,
        )

    def complete_unknown(self, physical_id: str, *, reason: str) -> None:
        self.ledger.settle_unknown_and_block(physical_id=physical_id, reason=reason)
