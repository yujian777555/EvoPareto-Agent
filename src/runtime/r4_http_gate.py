"""Host-side R4 HTTP pre-send gate (R8 — mandatory).

R4 send path MUST use ``ensure_r4_http_allowed`` / ``post_json_r4``.
If no gate is installed, R4 sends are **rejected** (fail closed).
Legacy R3 ``post_json`` is isolated: it only consults a gate when one is
installed (optional), and is not an R4 entry point.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_GATE: Optional[Callable[[], Optional[str]]] = None
SEND_ATTEMPTS = {"n": 0}
SEND_BLOCKED = {"n": 0}
R4_SENDS = {"n": 0}


class R4HttpBlocked(RuntimeError):
    """R4 execution authorization failed — no network send."""


def install_r4_http_gate(checker: Callable[[], Optional[str]]) -> None:
    global _GATE
    _GATE = checker


def clear_r4_http_gate() -> None:
    global _GATE
    _GATE = None


def r4_gate_installed() -> bool:
    return _GATE is not None


def ensure_r4_http_allowed() -> None:
    """R4 pre-send gate. No gate installed => BLOCKED."""
    SEND_ATTEMPTS["n"] += 1
    if _GATE is None:
        SEND_BLOCKED["n"] += 1
        raise R4HttpBlocked("R4_GATE_NOT_INSTALLED")
    err = _GATE()
    if err:
        SEND_BLOCKED["n"] += 1
        raise R4HttpBlocked(err)


def make_r4_real_checker(config: Dict[str, Any], ledger: Any, auth_path: Any = None) -> Callable[[], Optional[str]]:
    """Checker for the REAL path: loads controlled auth file; ledger required."""

    def _check() -> Optional[str]:
        from src.research.r4_execution_authorization import verify_execution_allowed_real

        return verify_execution_allowed_real(config, ledger=ledger, auth_path=auth_path)

    return _check


def post_json_r4(url: str, payload: Dict[str, Any], headers: Dict[str, str], **kwargs: Any):
    """R4-only HTTP entry. Always runs the mandatory gate first."""
    ensure_r4_http_allowed()
    R4_SENDS["n"] += 1
    from src.backend.http_client import post_json

    return post_json(url, payload, headers, **kwargs)


def make_r4_checker(config, auth_record, ledger=None):
    """TEST helper: inject-path checker (never use on real execution)."""

    def _check():
        from src.research.r4_execution_authorization import verify_execution_allowed_inject

        return verify_execution_allowed_inject(
            config,
            auth_record=auth_record,
            ledger=ledger if ledger is not None else {
                "blocked": False,
                "remaining_requests": 10**9,
                "remaining_tokens_in": 10**12,
                "remaining_tokens_out": 10**12,
                "remaining_usd": 1e6,
            },
        )

    return _check
