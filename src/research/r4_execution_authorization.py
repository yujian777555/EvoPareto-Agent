"""R4 execution authorization — separate from experiment freeze config.

Design (R7, closes P0 execution-gate bypass):

* Experiment freeze config holds protocol ONLY (no authorization flags).
* Authorization is a separate record bound to an exact ``config_sha256``.
* Status whitelist is strict: only ``AUTHORIZED`` may execute.
  Unknown / missing / DRAFT / PROPOSED / BLOCKED all fail closed.
* ``verify_execution_allowed`` always re-validates full config (structure +
  policy + seeds) before consulting authorization or budget.
* Real execution path uses ``load_execution_authorization`` (controlled file).
  Test injection uses ``AuthorizationRecord`` only in tests — never on the
  real path entry ``authorize_http_send``.

No real API. This module never opens network sockets.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "AUTHORIZED_STATUS",
    "FORBIDDEN_STATUSES",
    "AuthorizationRecord",
    "AuthorizationError",
    "make_test_authorization",
    "load_execution_authorization",
    "verify_execution_allowed",
    "authorize_http_send",
]

# Strict allow-list — anything not explicitly here is forbidden.
AUTHORIZED_STATUS = "AUTHORIZED"
# Freeze config status must also be explicitly approved (not merely "not forbidden")
CONFIG_STATUS_ALLOW = frozenset({"APPROVED_FOR_EXECUTION", "FROZEN_ACCEPTED"})
FORBIDDEN_STATUSES = frozenset(
    {
        "DRAFT",
        "PROPOSED",
        "PROPOSED_PENDING_PLANNER_ACCEPTANCE",
        "BLOCKED",
        "REJECTED",
        "EXPIRED",
        "REVOKED",
        "",
        "UNKNOWN",
        "NONE",
    }
)

AUTH_PATH_ENV = "EVOPARETO_R4_EXEC_AUTH"


class AuthorizationError(RuntimeError):
    """Authorization record missing, corrupt, or not bound to this config."""


@dataclass(frozen=True)
class AuthorizationRecord:
    """Binding of an execution grant to one exact freeze config.

    ``status`` must be exactly AUTHORIZED_STATUS to allow execution.
    ``source`` must be 'controlled_file' on the real path (tests use 'TEST').
    """

    status: str
    config_sha256: str
    experiment_version: str
    max_requests: int
    max_tokens_in: int
    max_tokens_out: int
    max_cost_usd: float
    source: str = "TEST"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "config_sha256": self.config_sha256,
            "experiment_version": self.experiment_version,
            "max_requests": self.max_requests,
            "max_tokens_in": self.max_tokens_in,
            "max_tokens_out": self.max_tokens_out,
            "max_cost_usd": self.max_cost_usd,
            "source": self.source,
        }


def make_test_authorization(config: Dict[str, Any], **overrides: Any) -> AuthorizationRecord:
    """TEST-ONLY constructor. Never used by the real execution path."""
    rec = AuthorizationRecord(
        status=AUTHORIZED_STATUS,
        config_sha256=str(config.get("config_sha256", "")),
        experiment_version=str(config.get("version", "")),
        max_requests=int(overrides.get("max_requests", 10**8)),
        max_tokens_in=int(overrides.get("max_tokens_in", 10**12)),
        max_tokens_out=int(overrides.get("max_tokens_out", 10**12)),
        max_cost_usd=float(overrides.get("max_cost_usd", 1e6)),
        source="TEST",
    )
    return rec


def load_execution_authorization(path: Optional[Path] = None) -> AuthorizationRecord:
    """Load controlled authorization file. Fail closed if missing/corrupt.

    This is the only loader allowed on the real execution path.
    """
    p = path
    if p is None:
        import os

        env = os.environ.get(AUTH_PATH_ENV)
        p = Path(env) if env else Path.home() / ".evopareto" / "state" / "r4_execution_authorization.json"
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
            max_requests=int(raw["max_requests"]),
            max_tokens_in=int(raw["max_tokens_in"]),
            max_tokens_out=int(raw["max_tokens_out"]),
            max_cost_usd=float(raw["max_cost_usd"]),
            source="controlled_file",
        )
    except Exception as exc:
        raise AuthorizationError("EXEC_AUTH_FIELD:%s" % type(exc).__name__) from exc
    return rec


def _controlled_auth_required(auth_record: Optional[AuthorizationRecord], *, allow_test: bool) -> str:
    if auth_record is None:
        return "EXEC_AUTH_MISSING"
    if auth_record.source != "controlled_file" and not allow_test:
        return "EXEC_AUTH_SOURCE_NOT_CONTROLLED:%s" % auth_record.source
    return ""


def verify_execution_allowed(
    config: Dict[str, Any],
    *,
    auth_record: Optional[AuthorizationRecord] = None,
    ledger: Optional[Any] = None,
    allow_test_injection: bool = False,
) -> str:
    """Single authorization contract. Fail closed. Never skips structure checks.

    Order (all mandatory):
      1. full config structure + hash + policy + seeds (re-validated here)
      2. authorization record present, status == AUTHORIZED, bound to config SHA
      3. auth_record source is controlled_file unless allow_test_injection
      4. ledger remaining budget (if provided) covers plan demand
    """
    # 1) always re-validate config — never trust prior validation
    from src.research.r4_exec_freeze import (
        _requirements_from_config,
        verify_budget_feasibility,
        verify_exec_config_structure,
    )

    err = verify_exec_config_structure(config)
    if err:
        return "EXEC_CONFIG_REJECTED:%s" % err

    # 1b) freeze status must be explicitly approved — PROPOSED/DRAFT/unknown fail
    cfg_status = str((config or {}).get("status", ""))
    if cfg_status not in CONFIG_STATUS_ALLOW:
        return "EXEC_CONFIG_STATUS_NOT_APPROVED:%s" % (cfg_status or "MISSING")

    # 2) authorization record
    err = _controlled_auth_required(auth_record, allow_test=allow_test_injection)
    if err:
        return err
    assert auth_record is not None
    if auth_record.status != AUTHORIZED_STATUS:
        return "EXEC_AUTH_STATUS_FORBIDDEN:%s" % (auth_record.status or "MISSING")
    if auth_record.status in FORBIDDEN_STATUSES:
        return "EXEC_AUTH_STATUS_FORBIDDEN:%s" % auth_record.status
    if not auth_record.config_sha256 or auth_record.config_sha256 != config.get("config_sha256"):
        return "EXEC_AUTH_CONFIG_SHA_MISMATCH"
    if not auth_record.experiment_version or auth_record.experiment_version != config.get("version"):
        return "EXEC_AUTH_VERSION_MISMATCH"
    if auth_record.max_requests <= 0 or auth_record.max_tokens_in <= 0 or auth_record.max_tokens_out <= 0:
        return "EXEC_AUTH_QUOTA_INVALID"
    if auth_record.max_cost_usd <= 0:
        return "EXEC_AUTH_COST_INVALID"

    # 3) budget vs remaining ledger (optional but required on real path)
    if ledger is not None:
        from src.research.r4_exec_freeze import AuthSnapshot

        if not isinstance(ledger, (dict, AuthSnapshot)):
            return "BUDGET_AUTH_TYPE"
        if ledger.get("blocked"):
            return "BUDGET_AUTH_BLOCKED"
        bc = config.get("budget_caps") or {}
        planned = bc.get("planned_r_values") or []
        for r in planned:
            try:
                req = _requirements_from_config(config, int(r))
            except Exception as exc:
                return "BUDGET_REQ_INVALID:%s" % exc
            err = verify_budget_feasibility(req, ledger)
            if err:
                return err
    return ""


def authorize_http_send(
    config: Dict[str, Any],
    *,
    auth_record: Optional[AuthorizationRecord] = None,
    ledger: Optional[Any] = None,
    allow_test_injection: bool = False,
) -> None:
    """TRUSTED host-side gate. Must be called BEFORE any network send.

    Raises AuthorizationError on any failure. Never returns "partial" allow.
    Container-generated code must not be able to reach HTTP without this gate
    on the host bridge.
    """
    err = verify_execution_allowed(
        config,
        auth_record=auth_record,
        ledger=ledger,
        allow_test_injection=allow_test_injection,
    )
    if err:
        raise AuthorizationError(err)
