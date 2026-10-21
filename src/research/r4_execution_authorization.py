"""R4 execution authorization (R8) — fail-closed, unforgeable-on-real-path.

Security contract
-----------------
* Real execution uses ``verify_execution_allowed_real`` which **loads the
  controlled authorization file itself** and **requires a verified ledger**.
  Caller-supplied objects are never trusted on the real path.
* ``source='controlled_file'`` on a hand-built object is **not** sufficient.
* Budget numerics: reject NaN/inf/bool/str; no implicit int()/float() escape.
* Multi-R plans use **cumulative** demand (scheme 1): sum over all
  ``planned_r_values`` before comparing to remaining quota.
* Test injection lives only in ``verify_execution_allowed_inject`` and is
  never reachable from ``authorize_http_send`` / R4 HTTP gate.

No network. No real credentials.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

__all__ = [
    "AUTHORIZED_STATUS",
    "CONFIG_STATUS_ALLOW",
    "AuthorizationRecord",
    "AuthorizationError",
    "make_test_authorization",
    "load_execution_authorization",
    "verify_execution_allowed_inject",
    "verify_execution_allowed_real",
    "authorize_http_send",
    "strict_number",
]

AUTHORIZED_STATUS = "AUTHORIZED"
CONFIG_STATUS_ALLOW = frozenset({"APPROVED_FOR_EXECUTION", "FROZEN_ACCEPTED"})
FORBIDDEN_STATUSES = frozenset(
    {"DRAFT", "PROPOSED", "PROPOSED_PENDING_PLANNER_ACCEPTANCE", "BLOCKED",
     "REJECTED", "EXPIRED", "REVOKED", "", "UNKNOWN", "NONE"}
)
AUTH_PATH_ENV = "EVOPARETO_R4_EXEC_AUTH"
DEFAULT_AUTH_PATH = Path.home() / ".evopareto" / "state" / "r4_execution_authorization.json"


class AuthorizationError(RuntimeError):
    pass


def strict_number(name: str, value: Any, *, integer: bool = False) -> float | int:
    """Reject bool/str/NaN/inf. No implicit coercion."""
    if isinstance(value, bool):
        raise AuthorizationError("NUM_TYPE:%s:bool" % name)
    if isinstance(value, str):
        raise AuthorizationError("NUM_TYPE:%s:str" % name)
    if integer:
        if isinstance(value, float):
            if not value.is_integer():
                raise AuthorizationError("NUM_TYPE:%s:float_not_int" % name)
            value = int(value)  # 6.0 -> 6 is still a type change; reject below
            raise AuthorizationError("NUM_TYPE:%s:float" % name)
        if not isinstance(value, int):
            raise AuthorizationError("NUM_TYPE:%s:%s" % (name, type(value).__name__))
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise AuthorizationError("NUM_NOT_FINITE:%s" % name)
        return value
    raise AuthorizationError("NUM_TYPE:%s:%s" % (name, type(value).__name__))


@dataclass(frozen=True)
class AuthorizationRecord:
    status: str
    config_sha256: str
    experiment_version: str
    max_requests: int
    max_tokens_in: int
    max_tokens_out: int
    max_cost_usd: float
    issued_at_unix: float = 0.0
    expires_at_unix: float = 0.0
    nonce: str = ""
    record_sha256: str = ""
    origin_path: str = ""
    source: str = "TEST"  # informational only — real path never trusts this alone


def _canonical_record_bytes(rec: AuthorizationRecord) -> bytes:
    body = {
        "status": rec.status,
        "config_sha256": rec.config_sha256,
        "experiment_version": rec.experiment_version,
        "max_requests": rec.max_requests,
        "max_tokens_in": rec.max_tokens_in,
        "max_tokens_out": rec.max_tokens_out,
        "max_cost_usd": rec.max_cost_usd,
        "issued_at_unix": rec.issued_at_unix,
        "expires_at_unix": rec.expires_at_unix,
        "nonce": rec.nonce,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_record_sha256(rec: AuthorizationRecord) -> str:
    return hashlib.sha256(_canonical_record_bytes(rec)).hexdigest()


def make_test_authorization(config: Dict[str, Any], **overrides: Any) -> AuthorizationRecord:
    """TEST-ONLY. Not accepted on the real path."""
    rec = AuthorizationRecord(
        status=overrides.get("status", AUTHORIZED_STATUS),
        config_sha256=str(overrides.get("config_sha256", config.get("config_sha256", ""))),
        experiment_version=str(overrides.get("experiment_version", config.get("version", ""))),
        max_requests=int(overrides.get("max_requests", 10**8)),
        max_tokens_in=int(overrides.get("max_tokens_in", 10**12)),
        max_tokens_out=int(overrides.get("max_tokens_out", 10**12)),
        max_cost_usd=float(overrides.get("max_cost_usd", 1e6)),
        issued_at_unix=float(overrides.get("issued_at_unix", 0.0)),
        expires_at_unix=float(overrides.get("expires_at_unix", 0.0)),
        nonce=str(overrides.get("nonce", "TEST-NONCE")),
        source="TEST",
    )
    rec = AuthorizationRecord(**{**rec.__dict__, "record_sha256": compute_record_sha256(rec)})
    return rec


def load_execution_authorization(path: Optional[Path] = None) -> AuthorizationRecord:
    """Load controlled file and verify self-hash. Fail closed."""
    p = path
    if p is None:
        env = os.environ.get(AUTH_PATH_ENV)
        p = Path(env) if env else DEFAULT_AUTH_PATH
    if not p.exists():
        raise AuthorizationError("EXEC_AUTH_FILE_MISSING")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise AuthorizationError("EXEC_AUTH_PARSE:%s" % type(exc).__name__) from exc
    if not isinstance(raw, dict):
        raise AuthorizationError("EXEC_AUTH_NOT_OBJECT")
    try:
        rec = AuthorizationRecord(
            status=str(raw.get("status", "")),
            config_sha256=str(raw.get("config_sha256", "")),
            experiment_version=str(raw.get("experiment_version", "")),
            max_requests=strict_number("max_requests", raw["max_requests"], integer=True),
            max_tokens_in=strict_number("max_tokens_in", raw["max_tokens_in"], integer=True),
            max_tokens_out=strict_number("max_tokens_out", raw["max_tokens_out"], integer=True),
            max_cost_usd=strict_number("max_cost_usd", raw["max_cost_usd"]),
            issued_at_unix=float(raw.get("issued_at_unix", 0.0)),
            expires_at_unix=float(raw.get("expires_at_unix", 0.0)),
            nonce=str(raw.get("nonce", "")),
            record_sha256=str(raw.get("record_sha256", "")),
            origin_path=str(p),
            source="controlled_file",
        )
    except AuthorizationError:
        raise
    except Exception as exc:
        raise AuthorizationError("EXEC_AUTH_FIELD:%s" % type(exc).__name__) from exc
    if not rec.nonce:
        raise AuthorizationError("EXEC_AUTH_NONCE_MISSING")
    expected = compute_record_sha256(rec)
    if rec.record_sha256 != expected:
        raise AuthorizationError("EXEC_AUTH_TAMPERED")
    return rec


def _validate_record_common(rec: AuthorizationRecord, config: Dict[str, Any], now: float) -> str:
    if rec.status != AUTHORIZED_STATUS:
        return "EXEC_AUTH_STATUS_FORBIDDEN:%s" % (rec.status or "MISSING")
    if rec.status in FORBIDDEN_STATUSES:
        return "EXEC_AUTH_STATUS_FORBIDDEN:%s" % rec.status
    if not rec.config_sha256 or rec.config_sha256 != config.get("config_sha256"):
        return "EXEC_AUTH_CONFIG_SHA_MISMATCH"
    if not rec.experiment_version or rec.experiment_version != config.get("version"):
        return "EXEC_AUTH_VERSION_MISMATCH"
    if rec.record_sha256 != compute_record_sha256(rec):
        return "EXEC_AUTH_TAMPERED"
    if rec.expires_at_unix and now > float(rec.expires_at_unix):
        return "EXEC_AUTH_EXPIRED"
    try:
        strict_number("max_requests", rec.max_requests, integer=True)
        strict_number("max_tokens_in", rec.max_tokens_in, integer=True)
        strict_number("max_tokens_out", rec.max_tokens_out, integer=True)
        mr = strict_number("max_requests", rec.max_requests, integer=True)
        mt_in = strict_number("max_tokens_in", rec.max_tokens_in, integer=True)
        mt_out = strict_number("max_tokens_out", rec.max_tokens_out, integer=True)
        mc = strict_number("max_cost_usd", rec.max_cost_usd)
    except AuthorizationError as exc:
        return str(exc)
    if mr <= 0 or mt_in <= 0 or mt_out <= 0 or mc <= 0:
        return "EXEC_AUTH_QUOTA_INVALID"
    return ""


def _ledger_remaining_check(ledger: Any) -> str:
    if ledger is None:
        return "BUDGET_LEDGER_REQUIRED"
    if not isinstance(ledger, dict):
        return "BUDGET_AUTH_TYPE"
    if ledger.get("blocked"):
        return "BUDGET_AUTH_BLOCKED"
    for key in ("remaining_requests", "remaining_tokens_in", "remaining_tokens_out", "remaining_usd"):
        if key not in ledger:
            return "BUDGET_REMAINING_MISSING:%s" % key
    try:
        for key in ("remaining_requests", "remaining_tokens_in", "remaining_tokens_out"):
            v = ledger[key]
            if isinstance(v, bool) or not isinstance(v, int):
                return "BUDGET_FIELDS_INVALID:%s" % key
            if v < 0:
                return "BUDGET_REMAINING_NEGATIVE"
        usd = ledger["remaining_usd"]
        if isinstance(usd, bool):
            return "BUDGET_FIELDS_INVALID:remaining_usd"
        usd = strict_number("remaining_usd", usd)
        if usd < 0:
            return "BUDGET_REMAINING_NEGATIVE"
        for key in ("consumed_requests", "spent_usd"):
            if key in ledger:
                strict_number(key, ledger[key])
    except AuthorizationError as exc:
        return str(exc)
    except Exception:
        return "BUDGET_FIELDS_INVALID"
    return ""


def _cumulative_requirements(config: Dict[str, Any]) -> str | Tuple[List[Any], int, int, int, float]:
    """Scheme 1 (R8): sum demand over ALL planned_r_values. Returns error or totals."""
    from src.research.r4_exec_freeze import _requirements_from_config
    from src.research.r4_exec_freeze import BudgetError

    bc = config.get("budget_caps") or {}
    planned = bc.get("planned_r_values")
    if not isinstance(planned, (list, tuple)) or not planned:
        return "BUDGET_PLANNED_R_INVALID"
    sum_req = sum_in = sum_out = 0
    sum_usd = 0.0
    reqs = []
    for r in planned:
        try:
            req = _requirements_from_config(config, int(r))
        except Exception as exc:
            return "BUDGET_REQ_INVALID:%s" % exc
        reqs.append(req)
        sum_req += int(req["requests_with_margin"])
        sum_in += int(req["tokens_in_with_margin"])
        sum_out += int(req["tokens_out_with_margin"])
        sum_usd += float(req["usd_with_margin"])
    return reqs, sum_req, sum_in, sum_out, sum_usd


def _check_budget_cumulative(config: Dict[str, Any], ledger: Dict[str, Any]) -> str:
    err = _ledger_remaining_check(ledger)
    if err:
        return err
    got = _cumulative_requirements(config)
    if isinstance(got, str):
        return got
    _reqs, sum_req, sum_in, sum_out, sum_usd = got
    rem_req = int(ledger["remaining_requests"])
    rem_in = int(ledger["remaining_tokens_in"])
    rem_out = int(ledger["remaining_tokens_out"])
    rem_usd = strict_number("remaining_usd", ledger["remaining_usd"])
    if sum_req > rem_req:
        return "BUDGET_REQUESTS_EXCEEDED:need=%d,remaining=%d" % (sum_req, rem_req)
    if sum_in > rem_in:
        return "BUDGET_TOKENS_IN_EXCEEDED:need=%d,remaining=%d" % (sum_in, rem_in)
    if sum_out > rem_out:
        return "BUDGET_TOKENS_OUT_EXCEEDED:need=%d,remaining=%d" % (sum_out, rem_out)
    if sum_usd > rem_usd + 1e-12:
        return "BUDGET_USD_EXCEEDED:need=%.6f,remaining=%.6f" % (sum_usd, rem_usd)
    return ""


def _core_checks(config: Dict[str, Any], rec: AuthorizationRecord, ledger: Any, now: float) -> str:
    from src.research.r4_exec_freeze import verify_exec_config_structure

    err = verify_exec_config_structure(config)
    if err:
        return "EXEC_CONFIG_REJECTED:%s" % err
    cfg_status = str((config or {}).get("status", ""))
    if cfg_status not in CONFIG_STATUS_ALLOW:
        return "EXEC_CONFIG_STATUS_NOT_APPROVED:%s" % (cfg_status or "MISSING")
    err = _validate_record_common(rec, config, now)
    if err:
        return err
    return _check_budget_cumulative(config, ledger if isinstance(ledger, dict) else ledger)


def verify_execution_allowed_inject(
    config: Dict[str, Any],
    *,
    auth_record: AuthorizationRecord,
    ledger: Any = None,
    now: Optional[float] = None,
    allow_test_injection: bool = True,
    **_ignored: Any,
) -> str:
    """TEST-ONLY verification. Never called from real HTTP path.

    ``allow_test_injection`` is accepted for API compatibility and is implied.
    ``ledger`` is still mandatory for budget checks (fail closed if None).
    """
    if auth_record is None:
        return "EXEC_AUTH_MISSING"
    return _core_checks(config, auth_record, ledger, float(now if now is not None else 0.0))


def verify_execution_allowed_real(
    config: Dict[str, Any],
    *,
    ledger: Any,
    auth_path: Optional[Path] = None,
    now: Optional[float] = None,
) -> str:
    """Real-path verification: loads controlled auth file; ledger mandatory."""
    if ledger is None:
        return "BUDGET_LEDGER_REQUIRED"
    try:
        rec = load_execution_authorization(auth_path)
    except AuthorizationError as exc:
        return str(exc)
    return _core_checks(config, rec, ledger, float(now if now is not None else __import__("time").time()))


def authorize_http_send(
    config: Dict[str, Any],
    *,
    ledger: Any = None,
    auth_path: Optional[Path] = None,
) -> None:
    """TRUSTED host-side gate. Loads controlled auth; requires ledger."""
    err = verify_execution_allowed_real(config, ledger=ledger, auth_path=auth_path)
    if err:
        raise AuthorizationError(err)
