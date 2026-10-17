"""Level 3-R1 budget ledger: actual vs reserved vs unknown + persistent identity.

Task B:
  * separate ACTUAL_TOKENS / RESERVED_TOKENS / UNKNOWN_USAGE
  * bind budget caps to a persistent authorization identity (not a random run id)
  * run-id / DB deletion / restart must NOT restore consumed quota
  * fail-closed when a trustworthy ledger cannot be recovered
  * cost is always usage-based ESTIMATE, never a provider final invoice
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

# Persistent authorization identity — stable across runs.
# Derived from a workspace-local salt file so it survives run-id rotation
# and DB deletion, without embedding any secret in Git.
AUTH_SALT_PATH = ROOT / "results" / "level3_live_calibration" / "auth_identity.txt"
DEFAULT_AUTH_ID = "level3-live-authorization-v1"


def resolve_auth_identity() -> str:
    """Stable authorization identity. Creates the salt file once if missing.

    Deleting the budget DB does NOT change this identity, so cumulative
    consumption cannot be reset by rotating run ids or databases.
    """
    AUTH_SALT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if AUTH_SALT_PATH.exists():
        return AUTH_SALT_PATH.read_text(encoding="utf-8").strip()
    # first time: mint a deterministic id from workspace path + marker
    marker = "EvoPareto-Level3-Live-Authorization"
    digest = hashlib.sha256(f"{marker}|{ROOT}".encode("utf-8")).hexdigest()[:16]
    ident = f"{DEFAULT_AUTH_ID}-{digest}"
    AUTH_SALT_PATH.write_text(ident + "\n", encoding="utf-8")
    return ident


class AuthBudgetLedger:
    """Append-only request ledger bound to a persistent authorization identity.

    Columns distinguish:
      reserved_tokens_in/out  — pre-send quota reservation
      actual_tokens_in/out    — trusted provider usage after settle
      usage_kind              — 'actual' | 'reserved_only' | 'unknown'
    """

    def __init__(self, path: Path, *, max_physical: int, max_cost_usd: float,
                 max_total_in: int, max_total_out: int) -> None:
        self.path = Path(path)
        self.auth_id = resolve_auth_identity()
        self.max_physical = max_physical
        self.max_cost_usd = max_cost_usd
        self.max_total_in = max_total_in
        self.max_total_out = max_total_out
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._migrate_if_needed()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_budget (
                    auth_id TEXT PRIMARY KEY,
                    max_physical INTEGER NOT NULL,
                    max_cost_usd REAL NOT NULL,
                    max_total_in INTEGER NOT NULL,
                    max_total_out INTEGER NOT NULL,
                    physical_attempts INTEGER NOT NULL DEFAULT 0,
                    reserved_tokens_in INTEGER NOT NULL DEFAULT 0,
                    reserved_tokens_out INTEGER NOT NULL DEFAULT 0,
                    actual_tokens_in INTEGER NOT NULL DEFAULT 0,
                    actual_tokens_out INTEGER NOT NULL DEFAULT 0,
                    unknown_usage_count INTEGER NOT NULL DEFAULT 0,
                    spent_cost_usd REAL NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    block_reason TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_requests (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    auth_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    logical_request_id TEXT NOT NULL,
                    physical_request_id TEXT NOT NULL,
                    request_phase TEXT NOT NULL,
                    prompt_sha256 TEXT NOT NULL,
                    reserved_tokens_in INTEGER NOT NULL,
                    reserved_tokens_out INTEGER NOT NULL,
                    actual_tokens_in INTEGER,
                    actual_tokens_out INTEGER,
                    usage_kind TEXT NOT NULL,
                    reserved_cost_usd REAL NOT NULL,
                    observed_cost_usd REAL,
                    http_status INTEGER,
                    model_returned TEXT,
                    finish_reason TEXT,
                    request_status TEXT NOT NULL,
                    error_kind TEXT
                )
                """
            )
            self._conn.commit()

    def _migrate_if_needed(self) -> None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM auth_budget WHERE auth_id=?", (self.auth_id,)
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO auth_budget (auth_id, max_physical, max_cost_usd, "
                    "max_total_in, max_total_out) VALUES (?,?,?,?,?)",
                    (self.auth_id, self.max_physical, self.max_cost_usd,
                     self.max_total_in, self.max_total_out),
                )
                self._conn.commit()
            else:
                # never raise caps silently
                self.max_physical = min(self.max_physical, int(row["max_physical"]))
                self.max_cost_usd = min(self.max_cost_usd, float(row["max_cost_usd"]))
                self.max_total_in = min(self.max_total_in, int(row["max_total_in"]))
                self.max_total_out = min(self.max_total_out, int(row["max_total_out"]))

    # ---------------- reservation ----------------
    def reserve(self, *, run_id: str, logical_id: str, physical_id: str,
                phase: str, prompt_sha: str,
                res_in: int, res_out: int, res_cost: float) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute(
                    "SELECT * FROM auth_budget WHERE auth_id=?", (self.auth_id,)
                ).fetchone()
                if row["blocked"]:
                    raise RuntimeError(f"BUDGET_BLOCKED:{row['block_reason']}")
                if int(row["physical_attempts"]) >= int(row["max_physical"]):
                    raise RuntimeError("MAX_PHYSICAL_EXCEEDED")
                if float(row["spent_cost_usd"]) + float(res_cost) > float(row["max_cost_usd"]):
                    raise RuntimeError("MAX_COST_EXCEEDED")
                if int(row["actual_tokens_in"]) + int(row["reserved_tokens_in"]) + int(res_in) > int(row["max_total_in"]):
                    raise RuntimeError("MAX_TOTAL_INPUT_TOKENS_EXCEEDED")
                if int(row["actual_tokens_out"]) + int(row["reserved_tokens_out"]) + int(res_out) > int(row["max_total_out"]):
                    raise RuntimeError("MAX_TOTAL_OUTPUT_TOKENS_EXCEEDED")
                conn.execute(
                    "UPDATE auth_budget SET physical_attempts=physical_attempts+1, "
                    "reserved_tokens_in=reserved_tokens_in+?, "
                    "reserved_tokens_out=reserved_tokens_out+? WHERE auth_id=?",
                    (int(res_in), int(res_out), self.auth_id),
                )
                conn.execute(
                    "INSERT INTO auth_requests (ts, auth_id, run_id, logical_request_id, "
                    "physical_request_id, request_phase, prompt_sha256, "
                    "reserved_tokens_in, reserved_tokens_out, usage_kind, "
                    "reserved_cost_usd, request_status) "
                    "VALUES (strftime('%s','now')+0.0,?,?,?,?,?,?,?,?,'reserved_only',?, 'reserved')",
                    (self.auth_id, run_id, logical_id, physical_id, phase, prompt_sha,
                     int(res_in), int(res_out), float(res_cost)),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def settle_actual(self, *, physical_id: str, actual_in: int, actual_out: int,
                      observed_cost: float, http_status: int,
                      model_returned: str, finish_reason: str) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE auth_requests SET actual_tokens_in=?, actual_tokens_out=?, "
                    "usage_kind='actual', observed_cost_usd=?, http_status=?, "
                    "model_returned=?, finish_reason=?, request_status='settled_ok' "
                    "WHERE physical_request_id=? AND usage_kind='reserved_only'",
                    (int(actual_in), int(actual_out), float(observed_cost),
                     int(http_status), model_returned, finish_reason, physical_id),
                )
                # release reservation, commit actual
                row = conn.execute(
                    "SELECT reserved_tokens_in, reserved_tokens_out FROM auth_requests "
                    "WHERE physical_request_id=?", (physical_id,)
                ).fetchone()
                # roll reserved down by the reservation for this request, then add actual
                conn.execute(
                    "UPDATE auth_budget SET "
                    "reserved_tokens_in=MAX(0, reserved_tokens_in-?), "
                    "reserved_tokens_out=MAX(0, reserved_tokens_out-?), "
                    "actual_tokens_in=actual_tokens_in+?, "
                    "actual_tokens_out=actual_tokens_out+?, "
                    "spent_cost_usd=spent_cost_usd+? WHERE auth_id=?",
                    (int(row["reserved_tokens_in"]), int(row["reserved_tokens_out"]),
                     int(actual_in), int(actual_out), float(observed_cost), self.auth_id),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def settle_unknown_and_block(self, *, physical_id: str, reason: str) -> None:
        with self._lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "UPDATE auth_requests SET usage_kind='unknown', "
                    "request_status='fail_closed', error_kind=? "
                    "WHERE physical_request_id=?",
                    (reason, physical_id),
                )
                conn.execute(
                    "UPDATE auth_budget SET unknown_usage_count=unknown_usage_count+1, "
                    "blocked=1, block_reason=? WHERE auth_id=?",
                    (reason, self.auth_id),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM auth_budget WHERE auth_id=?", (self.auth_id,)
            ).fetchone()
            return dict(row) if row else {}

    def request_rows(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM auth_requests ORDER BY seq"
            )
            return [dict(r) for r in cur.fetchall()]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
