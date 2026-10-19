"""Cross-process atomic authorization ledger (Level 3-R2.1 Tasks A/B/C).

Fixes over R2:
  1. snapshot() exposes an explicit, documented schema (flat + nested) so the
     production live script can never confuse reserved with actual tokens.
  2. The production entry NEVER auto-creates quota. open_existing() fails closed
     on a missing/corrupt record. New quota requires explicit create_authorization().
     Legacy Level 3 usage is imported by an explicit, idempotent migration.
  3. All reserve/settle operations take a real cross-process OS file lock, re-read
     the latest record inside that lock, validate, then atomically persist. A
     stale in-process _body is never written over a newer record.

Crash window: record persist is write-temp + fsync + os.replace. The working DB
transaction and the record persist are ordered so that a crash between them
leaves the record at least as conservative as the DB (record update happens
after the DB commit for reserves; a crash then leaves an unused reservation,
which is safe. For settles, the record is updated after the DB too — a crash
leaves outstanding reservation, also conservative). A missing record entry is
never interpreted as zero consumption.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]

# ---- cross-platform OS file lock ----
if os.name == "nt":
    import msvcrt

    @contextmanager
    def _file_lock(fh):
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    @contextmanager
    def _file_lock(fh):
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


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
    """Trusted checksummed cumulative-usage record.

    Every mutation goes through mutate() which:
      1. acquires the OS file lock (cross-process)
      2. re-reads the record from disk (never trusts a stale _body)
      3. applies the mutator
      4. write-temp + fsync + os.replace
    """

    def __init__(self, path: Path, secret_key: str) -> None:
        self.path = Path(path)
        self._key = secret_key
        self._lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        self._thread_lock = threading.RLock()
        self._poisoned: str = ""
        self._body: Dict[str, Any] = {}
        self._reload()

    # ---------- file helpers ----------
    def _reload(self) -> None:
        fault = self.path.with_suffix(self.path.suffix + ".PERSIST_FAULT")
        if fault.exists():
            raise AuthorizationIntegrityError(
                f"PERSIST_FAULT_MARKER_PRESENT:{fault.read_text(encoding='utf-8')[:200]}"
            )
        if not self.path.exists():
            raise AuthorizationMissing(f"AUTHORIZATION_RECORD_MISSING:{self.path}")
        try:
            body = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            raise AuthorizationIntegrityError(f"AUTHORIZATION_UNREADABLE:{e}") from e
        stored = body.get("integrity")
        expect = _integrity_of(body, self._key)
        if not stored or stored != expect:
            raise AuthorizationIntegrityError("AUTHORIZATION_INTEGRITY_MISMATCH")
        self._body = body

    def _persist(self) -> None:
        self._body["integrity"] = _integrity_of(self._body, self._key)
        tmp = self.path.with_suffix(self.path.suffix + f".tmp{os.getpid()}-{uuid.uuid4().hex[:6]}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(self._body, indent=2, ensure_ascii=False))
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        except Exception as e:
            # persistence failure -> the authorization state is untrustworthy.
            # Fail closed: this record object refuses further operations AND a
            # durable fault marker is written so a restarted process also
            # refuses (cross-process fail-closed).
            self._poisoned = f"PERSIST_FAILED:{type(e).__name__}:{e}"
            # The fault marker MUST land on disk. If the same filesystem also
            # refuses this write we cannot provide a cross-process guarantee —
            # surface that explicitly rather than pretending we can.
            fault = self.path.with_suffix(self.path.suffix + ".PERSIST_FAULT")
            try:
                fault.write_text(self._poisoned, encoding="utf-8")
            except Exception as marker_err:
                self._poisoned = (
                    f"NEITHER_RECORD_NOR_FAULT_MARKER_WRITABLE:"
                    f"{type(e).__name__}/{type(marker_err).__name__}"
                )
                # raise a distinct error so callers know the cross-process
                # fail-closed latch could not be armed
                raise RuntimeError(
                    "PROTECTION_NOT_PERSISTABLE: both the record write and the "
                    "fault-marker write failed; cross-process fail-closed cannot "
                    "be guaranteed on this filesystem. Manual recovery required."
                ) from e
            raise

    @contextmanager
    def _exclusive(self):
        if getattr(self, "_poisoned", None):
            raise AuthorizationIntegrityError(
                f"RECORD_POISONED_AFTER_PERSIST_FAILURE:{self._poisoned}"
            )
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "a+b") as fh:
            with _file_lock(fh):
                with self._thread_lock:
                    self._reload()  # always latest
                    yield
                    self._persist()

    # ---------- factories ----------
    @staticmethod
    def create(path: Path, *, auth_id: str, caps: Dict[str, Any], secret_key: str) -> "AuthorizationRecord":
        path = Path(path)
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+b") as fh:
            with _file_lock(fh):
                if path.exists():
                    raise AuthorizationError(
                        f"AUTHORIZATION_ALREADY_EXISTS:{path} — new quota requires "
                        "an explicit re-authorization procedure"
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
                    "migrations": [],
                }
                body["integrity"] = _integrity_of(body, secret_key)
                tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
                with open(tmp, "w", encoding="utf-8") as out:
                    out.write(json.dumps(body, indent=2, ensure_ascii=False))
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(tmp, path)
        return AuthorizationRecord(path, secret_key)

    @staticmethod
    def open_existing(path: Path, *, secret_key: str) -> "AuthorizationRecord":
        """Fail-closed load. NEVER mints quota."""
        return AuthorizationRecord(path, secret_key)

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

    def snapshot_flat(self) -> Dict[str, Any]:
        """Explicit flat schema for production callers."""
        c = self._body["consumed"]
        return {
            "auth_id": self._body["auth_id"],
            "physical_attempts": int(c["physical_attempts"]),
            "actual_tokens_in": int(c["actual_tokens_in"]),
            "actual_tokens_out": int(c["actual_tokens_out"]),
            "reserved_tokens_in": int(c.get("reserved_tokens_in") or 0),
            "reserved_tokens_out": int(c.get("reserved_tokens_out") or 0),
            "outstanding_reserved_cost_usd": float(c.get("outstanding_reserved_cost_usd") or 0.0),
            "spent_cost_usd": float(c["spent_cost_usd"]),
            "unknown_usage_count": int(c.get("unknown_usage_count") or 0),
            "blocked": bool(self._body.get("blocked")),
            "block_reason": self._body.get("block_reason"),
            "max_physical": int(self._body["caps"]["max_physical"]),
            "max_cost_usd": float(self._body["caps"]["max_cost_usd"]),
            "max_total_in": int(self._body["caps"]["max_total_in"]),
            "max_total_out": int(self._body["caps"]["max_total_out"]),
            "remaining_physical": self.remaining_physical(),
        }

    # ---------- mutation under cross-process lock ----------
    def mutate(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        with self._exclusive():
            fn(self._body)

    # ---------- legacy migration (explicit, idempotent) ----------
    def migrate_legacy_level3(self, ledger_json: Path, *, expected_sha256: str = "") -> Dict[str, Any]:
        """One-shot import of the Level 3 live request ledger. Idempotent.

        Verifies source integrity against the known historical baseline:
          2 requests, 162 input tokens, 454 output tokens, $0.0005934.
        Never issues an HTTP request.
        """
        ledger_json = Path(ledger_json)
        if not ledger_json.exists():
            raise AuthorizationError(f"LEGACY_LEDGER_MISSING:{ledger_json}")
        raw = ledger_json.read_bytes()
        src_sha = hashlib.sha256(raw).hexdigest()
        if expected_sha256 and src_sha != expected_sha256:
            raise AuthorizationIntegrityError(
                f"LEGACY_LEDGER_SHA_MISMATCH:{src_sha}!={expected_sha256}"
            )
        data = json.loads(raw.decode("utf-8"))
        rows = data.get("rows") or []
        n_req = len(rows)
        ain = sum(int(r.get("usage_prompt_tokens") or 0) for r in rows)
        aout = sum(int(r.get("usage_completion_tokens") or 0) for r in rows)
        cost = sum(float(r.get("observed_cost_usd") or 0.0) for r in rows)
        # verification baseline from the Planner
        if not (n_req == 2 and ain == 162 and aout == 454):
            raise AuthorizationIntegrityError(
                f"LEGACY_BASELINE_MISMATCH: n={n_req} in={ain} out={aout}"
            )
        if abs(cost - 0.0005934) > 1e-9:
            raise AuthorizationIntegrityError(
                f"LEGACY_COST_MISMATCH: {cost} != 0.0005934"
            )

        pids = [str(r.get("physical_request_id") or f"legacy-{i}") for i, r in enumerate(rows)]

        def _mut(body: Dict[str, Any]) -> None:
            migs = body.setdefault("migrations", [])
            for m in migs:
                if m.get("source_sha256") == src_sha and m.get("status") == "APPLIED":
                    return  # idempotent: already migrated this exact source
            c = body["consumed"]
            c["physical_attempts"] = int(c["physical_attempts"]) + n_req
            c["actual_tokens_in"] = int(c["actual_tokens_in"]) + ain
            c["actual_tokens_out"] = int(c["actual_tokens_out"]) + aout
            c["spent_cost_usd"] = float(c["spent_cost_usd"]) + cost
            migs.append({
                "status": "APPLIED",
                "source_file": str(ledger_json),
                "source_sha256": src_sha,
                "n_requests": n_req,
                "actual_tokens_in": ain,
                "actual_tokens_out": aout,
                "cost_usd_estimate": cost,
                "physical_request_ids": pids,
                "applied_at": time.time(),
            })
            body.setdefault("history_tail", []).append({
                "kind": "LEGACY_MIGRATION", "n": n_req, "sha": src_sha[:16],
            })

        self.mutate(_mut)
        return {
            "migrated": True, "n_requests": n_req,
            "actual_tokens_in": ain, "actual_tokens_out": aout,
            "cost_usd_estimate": cost, "source_sha256": src_sha,
        }


# ---------------------------------------------------------------------------
# Working DB (per-session detail) — deletable; rehydrates from the record
# ---------------------------------------------------------------------------
class AuthBudgetLedger:
    def __init__(self, working_db: Path, record: AuthorizationRecord) -> None:
        self.working_db = Path(working_db)
        self.record = record
        self._thread_lock = threading.RLock()
        self.working_db.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.working_db), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._rehydrate_from_record()

    def _init_schema(self) -> None:
        with self._thread_lock:
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

    def recover_stale_reservations(self) -> int:
        """Convert RESERVED rows left by a crashed process into unknown billing.

        A crash between the HTTP send and the settlement leaves a RESERVED row
        whose cost is unknowable. Conservative policy: mark SETTLED_UNKNOWN_BLOCKED
        and persist a billing block. Returns the number of rows recovered.
        """
        with self._thread_lock:
            rows = self._conn.execute(
                "SELECT physical_request_id FROM requests WHERE state=?",
                (STATE_RESERVED,),
            ).fetchall()
            stale = [r["physical_request_id"] for r in rows]
        for pid in stale:
            try:
                self.settle_unknown_and_block(
                    physical_id=pid, reason="CRASH_RECOVERY_UNKNOWN_BILLING"
                )
            except DuplicateSettlement:
                pass
        return len(stale)

    def _rehydrate_from_record(self) -> None:
        with self._thread_lock:
            row = self._conn.execute("SELECT COUNT(*) AS c FROM requests").fetchone()
            n_local = int(row["c"])
            n_record = int(self.record.consumed["physical_attempts"])
            if n_record > n_local:
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

    # ---------------- lifecycle ----------------
    def reserve(self, *, run_id: str, logical_id: str, physical_id: str,
                phase: str, prompt_sha: str, res_in: int, res_out: int,
                res_cost: float) -> None:
        if not physical_id or len(physical_id) < 8:
            raise AuthorizationError("PHYSICAL_ID_INVALID")

        # 1) insert into working DB (unique pid enforced)
        with self._thread_lock:
            conn = self._conn
            conn.execute("BEGIN IMMEDIATE")
            try:
                dup = conn.execute(
                    "SELECT state FROM requests WHERE physical_request_id=?", (physical_id,)
                ).fetchone()
                if dup is not None:
                    raise DuplicatePhysicalRequest(physical_id)
                conn.execute(
                    "INSERT INTO requests (physical_request_id, auth_id, run_id, "
                    "logical_request_id, request_phase, prompt_sha256, state, "
                    "reserved_tokens_in, reserved_tokens_out, reserved_cost_usd, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (physical_id, self.record.auth_id, run_id, logical_id, phase,
                     prompt_sha, STATE_RESERVED, int(res_in), int(res_out),
                     float(res_cost), time.time()),
                )
                conn.execute("COMMIT")
            except Exception:
                try:
                    conn.execute("ROLLBACK")
                except Exception:
                    pass
                raise

        # 2) update the trusted record under the CROSS-PROCESS lock
        def _mut(body: Dict[str, Any]) -> None:
            if body.get("blocked"):
                raise UnknownBillingBlocked(str(body.get("block_reason")))
            # cross-DB uniqueness: the record is the global authority
            seen = body.setdefault("physical_ids", [])
            if physical_id in seen:
                raise DuplicatePhysicalRequest(physical_id)
            caps = body["caps"]
            c = body["consumed"]
            if int(c["physical_attempts"]) + 1 > int(caps["max_physical"]):
                raise BudgetExceeded("MAX_PHYSICAL_EXCEEDED")
            outstanding = float(c.get("outstanding_reserved_cost_usd") or 0.0)
            if float(c["spent_cost_usd"]) + outstanding + float(res_cost) > float(caps["max_cost_usd"]):
                raise BudgetExceeded("MAX_COST_EXCEEDED")
            if int(c["actual_tokens_in"]) + int(c.get("reserved_tokens_in") or 0) + int(res_in) > int(caps["max_total_in"]):
                raise BudgetExceeded("MAX_TOTAL_INPUT_TOKENS_EXCEEDED")
            if int(c["actual_tokens_out"]) + int(c.get("reserved_tokens_out") or 0) + int(res_out) > int(caps["max_total_out"]):
                raise BudgetExceeded("MAX_TOTAL_OUTPUT_TOKENS_EXCEEDED")
            c["physical_attempts"] = int(c["physical_attempts"]) + 1
            c["reserved_tokens_in"] = int(c.get("reserved_tokens_in") or 0) + int(res_in)
            c["reserved_tokens_out"] = int(c.get("reserved_tokens_out") or 0) + int(res_out)
            c["outstanding_reserved_cost_usd"] = outstanding + float(res_cost)
            seen.append(physical_id)
            body.setdefault("history_tail", []).append(
                {"kind": "RESERVED", "pid": physical_id, "cost": float(res_cost)}
            )

        try:
            self.record.mutate(_mut)
        except Exception:
            # budget rejected AFTER local insert: mark row failed so the DB
            # cannot later look like a successful reservation
            with self._thread_lock:
                self._conn.execute(
                    "UPDATE requests SET state=?, error_kind=? WHERE physical_request_id=?",
                    (STATE_SETTLED_UNKNOWN_BLOCKED, "RESERVE_REJECTED_POST_INSERT", physical_id),
                )
                self._conn.commit()
            raise

    def settle_actual(self, *, physical_id: str, actual_in: int, actual_out: int,
                      observed_cost: float, http_status: int, model_returned: str,
                      finish_reason: str) -> None:
        with self._thread_lock:
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

        # Task A (R2.1): ONE lock operation performs
        #   cap check -> block write -> audit of actual usage -> reservation release.
        # No second mutate; no window where a concurrent reserve can slip through.
        outcome = {"over": None, "reason": ""}

        def _mut(body: Dict[str, Any]) -> None:
            caps = body["caps"]
            c = body["consumed"]
            remaining_reserved_in = max(0, int(c.get("reserved_tokens_in") or 0) - reserved_in)
            remaining_reserved_out = max(0, int(c.get("reserved_tokens_out") or 0) - reserved_out)
            remaining_outstanding_cost = max(
                0.0, float(c.get("outstanding_reserved_cost_usd") or 0.0) - reserved_cost
            )
            new_in = int(c["actual_tokens_in"]) + int(actual_in)
            new_out = int(c["actual_tokens_out"]) + int(actual_out)
            new_spent = float(c["spent_cost_usd"]) + float(observed_cost)

            over_reason = ""
            if new_spent + remaining_outstanding_cost > float(caps["max_cost_usd"]) + 1e-9:
                over_reason = (
                    f"ACTUAL_COST_EXCEEDS_CAP:spent={new_spent}"
                    f"+outstanding={remaining_outstanding_cost}>{caps['max_cost_usd']}"
                )
            elif new_in > int(caps["max_total_in"]):
                over_reason = f"ACTUAL_INPUT_TOKENS_EXCEED_CAP:{new_in}>{caps['max_total_in']}"
            elif new_out > int(caps["max_total_out"]):
                over_reason = f"ACTUAL_OUTPUT_TOKENS_EXCEED_CAP:{new_out}>{caps['max_total_out']}"

            # ALWAYS release this request's reservation and record its actual
            # usage — even when over cap — so the evidence is never lost.
            c["outstanding_reserved_cost_usd"] = remaining_outstanding_cost
            c["reserved_tokens_in"] = remaining_reserved_in
            c["reserved_tokens_out"] = remaining_reserved_out
            if over_reason:
                # keep the actual usage as evidence but do NOT add it to the
                # committed spend (the request is anomalous); block instead.
                body["blocked"] = True
                body["block_reason"] = over_reason
                body.setdefault("history_tail", []).append({
                    "kind": "BLOCK_ON_SETTLE", "pid": physical_id, "reason": over_reason,
                    "actual_in": int(actual_in), "actual_out": int(actual_out),
                    "observed_cost": float(observed_cost),
                })
                outcome["over"] = True
                outcome["reason"] = over_reason
                return
            c["actual_tokens_in"] = new_in
            c["actual_tokens_out"] = new_out
            c["spent_cost_usd"] = new_spent
            body.setdefault("history_tail", []).append({
                "kind": "SETTLED_ACTUAL", "pid": physical_id, "cost": float(observed_cost),
            })
            outcome["over"] = False

        # single persist covers check + block + audit
        self.record.mutate(_mut)

        if outcome["over"]:
            # DB row already written with the actual usage above; mark it as
            # an anomalous settlement so the evidence stays queryable.
            with self._thread_lock:
                self._conn.execute(
                    "UPDATE requests SET state=?, error_kind=? WHERE physical_request_id=?",
                    (STATE_SETTLED_UNKNOWN_BLOCKED, outcome["reason"], physical_id),
                )
                self._conn.commit()
            raise BudgetExceeded(outcome["reason"])

    def settle_unknown_and_block(self, *, physical_id: str, reason: str) -> None:
        with self._thread_lock:
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

        def _mut(body: Dict[str, Any]) -> None:
            body["blocked"] = True
            body["block_reason"] = reason
            c = body["consumed"]
            c["unknown_usage_count"] = int(c.get("unknown_usage_count") or 0) + 1
            c["outstanding_reserved_cost_usd"] = max(
                0.0, float(c.get("outstanding_reserved_cost_usd") or 0.0) - reserved_cost
            )
            c["spent_cost_usd"] = float(c["spent_cost_usd"]) + reserved_cost
            body.setdefault("history_tail", []).append(
                {"kind": "SETTLED_UNKNOWN_BLOCKED", "pid": physical_id, "reason": reason}
            )

        self.record.mutate(_mut)

    # ---------------- queries ----------------
    def request_rows(self) -> List[Dict[str, Any]]:
        with self._thread_lock:
            cur = self._conn.execute("SELECT * FROM requests ORDER BY seq")
            return [dict(r) for r in cur.fetchall()]

    def snapshot(self) -> Dict[str, Any]:
        """Documented schema — flat fields first, nested copy for detail.

        physical_attempts      — lifetime physical HTTP attempts (trusted record)
        actual_tokens_in/out   — provider-reported usage after settlement
        reserved_tokens_in/out — outstanding pre-send token reservations
        outstanding_reserved_cost_usd — $ reserved but not yet settled
        spent_cost_usd         — settled actual cost estimate (unknown billing
                                 counts the reservation as spent, conservatively)
        blocked / block_reason — persistent fail-closed flag
        """
        flat = self.record.snapshot_flat()
        rows = self.request_rows()
        return {
            **flat,
            "consumed": self.record.consumed,
            "caps": self.record.caps,
            "local_request_rows": len(rows),
            "schema_version": "r2.1",
        }

    def close(self) -> None:
        with self._thread_lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# Unified gate
# ---------------------------------------------------------------------------
class UnifiedBudgetGate:
    def __init__(self, ledger: AuthBudgetLedger, *, default_max_in: int, default_max_out: int) -> None:
        self.ledger = ledger
        self.default_max_in = default_max_in
        self.default_max_out = default_max_out

    def begin_request(self, *, run_id: str, phase: str, prompt_sha: str,
                      res_in: int, res_out: int, res_cost: float) -> str:
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


# ---------------------------------------------------------------------------
# Production entry helper (Tasks A/B): NEVER auto-creates quota
# ---------------------------------------------------------------------------
def open_production_authorization(
    record_path: Path,
    *,
    secret_key: str,
    legacy_ledger: Optional[Path] = None,
    legacy_expected_sha256: str = "",
) -> AuthorizationRecord:
    """Open an existing authorization for production use. Fail-closed.

    If `legacy_ledger` is given and the record has no matching migration,
    run the explicit idempotent import. NEVER creates a new authorization.
    """
    record = AuthorizationRecord.open_existing(Path(record_path), secret_key=secret_key)
    if legacy_ledger is not None:
        record.migrate_legacy_level3(
            Path(legacy_ledger), expected_sha256=legacy_expected_sha256
        )
    return record
