"""Host-side R4 HTTP pre-send gate (trusted boundary).

When a gate is installed, ``post_json`` and Gateway send paths MUST call
``ensure_r4_http_allowed`` before any socket. Container code cannot install
or clear this gate — it lives on the host process only.

Default: no gate installed → existing R3/historical paths unchanged.
R4 real execution requires an installed gate that passes verify_execution_allowed.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional

_GATE: Optional[Callable[[], Optional[str]]] = None
SEND_ATTEMPTS = {"n": 0}
SEND_BLOCKED = {"n": 0}


class R4HttpBlocked(RuntimeError):
    """R4 execution authorization failed — no network send."""


def install_r4_http_gate(checker: Callable[[], Optional[str]]) -> None:
    """Install host-side pre-send checker returning '' or an error code."""
    global _GATE
    _GATE = checker


def clear_r4_http_gate() -> None:
    global _GATE
    _GATE = None


def ensure_r4_http_allowed() -> None:
    """Called by transport BEFORE any socket send. Raises R4HttpBlocked."""
    SEND_ATTEMPTS["n"] += 1
    if _GATE is None:
        return  # not in R4 gated mode
    err = _GATE()
    if err:
        SEND_BLOCKED["n"] += 1
        raise R4HttpBlocked(err)


def make_r4_checker(config: Dict[str, Any], auth_record: Any, ledger: Any = None) -> Callable[[], Optional[str]]:
    def _check() -> Optional[str]:
        from src.research.r4_execution_authorization import verify_execution_allowed

        return verify_execution_allowed(
            config,
            auth_record=auth_record,
            ledger=ledger,
            allow_test_injection=False,
        )

    return _check
