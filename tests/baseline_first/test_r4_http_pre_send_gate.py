"""HTTP pre-send gate integration (mock). Asserts 0 network sends on reject."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backend.http_client import post_json
from src.research.r4_exec_freeze import DEFAULT_EXEC_FREEZE, canonical_config_sha256
from src.research.r4_execution_authorization import make_test_authorization
from src.runtime.r4_http_gate import (
    SEND_ATTEMPTS,
    SEND_BLOCKED,
    R4HttpBlocked,
    clear_r4_http_gate,
    install_r4_http_gate,
    make_r4_real_checker as make_r4_checker,
)

SOCKET_CONNECTS = {"n": 0}


@pytest.fixture(autouse=True)
def _count_sockets(monkeypatch):
    real = socket.socket.connect

    def spy(self, *a, **k):
        SOCKET_CONNECTS["n"] += 1
        raise OSError("NETWORK_BLOCKED")

    monkeypatch.setattr(socket.socket, "connect", spy)
    yield
    clear_r4_http_gate()


def test_proposed_config_blocks_post_json_before_socket():
    rec = make_test_authorization(DEFAULT_EXEC_FREEZE)  # PROPOSED config
    install_r4_http_gate(make_r4_checker(DEFAULT_EXEC_FREEZE, rec))
    before = SEND_BLOCKED["n"]
    with pytest.raises(R4HttpBlocked):
        post_json("http://127.0.0.1:9/chat", {"q": 1}, {}, max_retries=0)
    assert SEND_BLOCKED["n"] == before + 1
    assert SOCKET_CONNECTS["n"] == 0


def test_missing_auth_blocks_post_json():
    install_r4_http_gate(lambda: "EXEC_AUTH_MISSING")
    with pytest.raises(R4HttpBlocked):
        post_json("http://127.0.0.1:9/chat", {}, {}, max_retries=0)
    assert SOCKET_CONNECTS["n"] == 0


def test_budget_exceeded_blocks_post_json():
    install_r4_http_gate(lambda: "BUDGET_REQUESTS_EXCEEDED:need=528,remaining=56")
    with pytest.raises(R4HttpBlocked) as ei:
        post_json("http://127.0.0.1:9/chat", {}, {}, max_retries=0)
    assert "BUDGET_REQUESTS_EXCEEDED" in str(ei.value)
    assert SOCKET_CONNECTS["n"] == 0


def test_no_gate_keeps_legacy_path_socket_broken_not_auth_error():
    """Without R4 gate, transport may attempt socket (then fail on network block)."""
    clear_r4_http_gate()
    try:
        post_json("http://127.0.0.1:9/chat", {}, {}, max_retries=0)
    except R4HttpBlocked:
        pytest.fail("R4 gate must be inactive when not installed")
    except Exception:
        pass  # transport error expected
    assert SOCKET_CONNECTS["n"] <= 1  # at most one attempt; not an auth block
