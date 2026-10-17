"""Sandbox + controlled model IPC E2E (Stage 3.0-P1-R2A-R1 Task 4)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

docker_ok = True
try:
    import subprocess

    _r = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=15)
    docker_ok = _r.returncode == 0
except Exception:
    docker_ok = False

pytestmark = pytest.mark.skipif(not docker_ok, reason="docker daemon not running")

from src.runtime.http_budget import BudgetDB, PhysicalBudgetGate, install_global_gate
from src.runtime.provider_gateway import GatewayLLM, MockHTTPProvider, RequestLedger
from src.runtime.workflow_ipc import (
    ModelIPCServer,
    run_workflow_code_isolated,
)


@pytest.fixture()
def budget_llm(tmp_path):
    db = BudgetDB(tmp_path / "ipc.sqlite", max_physical=50, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(
        base_url=provider.base_url,
        ledger=ledger,
        run_id="sandbox-ipc",
        timeout=8.0,
    )
    yield {"llm": llm, "db": db, "ledger": ledger, "provider": provider}
    install_global_gate(None, strict=False)
    provider.shutdown()
    db.close()


GRAPH_USES_LLM = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        return await self.llm('solve: ' + problem)\n"
)

GRAPH_NETWORK_PROBE = (
    "class Workflow:\n"
    "    def __init__(self, llm=None):\n"
    "        self.llm = llm\n"
    "    async def __call__(self, problem):\n"
    "        import os, socket\n"
    "        secret = os.environ.get('R2A_HOST_SECRET')\n"
    "        try:\n"
    "            socket.create_connection(('1.1.1.1', 443), timeout=2)\n"
    "            net = 'OPEN'\n"
    "        except Exception as e:\n"
    "            net = type(e).__name__\n"
    "        sock = os.path.exists('/var/run/docker.sock')\n"
    "        return {'secret': secret, 'net': net, 'docker_sock': sock, 'via': 'ipc'}\n"
)


def test_workflow_reaches_model_only_via_ipc(budget_llm):
    """Untrusted Workflow runs with --network none but can still call the model
    through the controlled /ipc mailbox — and that request is budget-gated."""
    os.environ["R2A_HOST_SECRET"] = "should-not-leak"
    try:
        res = run_workflow_code_isolated(GRAPH_USES_LLM, llm=budget_llm["llm"], timeout=20)
    finally:
        os.environ.pop("R2A_HOST_SECRET", None)
    assert res["ok"] is True, res
    assert res["ipc_processed"], "no IPC request was processed — model path not used"
    assert all(p["ok"] for p in res["ipc_processed"])
    # budget ledger saw the physical HTTP behind the IPC
    rows = budget_llm["ledger"].rows()
    assert rows and rows[0]["request_status"] == "settled_ok"
    assert budget_llm["provider"].requests_seen


def test_workflow_network_denied_and_secrets_denied(budget_llm):
    os.environ["R2A_HOST_SECRET"] = "should-not-leak"
    try:
        res = run_workflow_code_isolated(GRAPH_NETWORK_PROBE, llm=budget_llm["llm"], timeout=20)
    finally:
        os.environ.pop("R2A_HOST_SECRET", None)
    assert res["ok"] is True, res
    out = res["stdout"]
    assert "should-not-leak" not in out
    assert "OPEN" not in out
    assert "'net': 'OSError'" in out or "'net': 'timeout'" in out.lower() or "OSError" in out


def test_ipc_server_is_the_only_model_channel(tmp_path):
    """ModelIPCServer drains /ipc/out via GatewayLLM — not via raw sockets."""
    db = BudgetDB(tmp_path / "ipc2.sqlite", max_physical=10, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="ipc-unit")
    ipc = tmp_path / "ipc"
    server = ModelIPCServer(ipc, llm)
    server.start()
    try:
        rid = "abc123"
        (ipc / "out" / f"{rid}.json").write_text(
            '{"id": "abc123", "prompt": "hello", "model": "deepseek-flash"}',
            encoding="utf-8",
        )
        import time

        deadline = time.time() + 5
        while time.time() < deadline and not (ipc / "in" / f"{rid}.json").exists():
            time.sleep(0.05)
        resp = (ipc / "in" / f"{rid}.json").read_text(encoding="utf-8")
        assert '"ok": true' in resp
        assert ledger.rows()
    finally:
        server.stop()
        install_global_gate(None, strict=False)
        provider.shutdown()
        db.close()


def test_ipc_fail_closed_when_budget_exhausted(tmp_path):
    db = BudgetDB(tmp_path / "ipc3.sqlite", max_physical=1, max_cost_usd=1.0)
    gate = PhysicalBudgetGate(db, est_cost_per_request=0.01)
    install_global_gate(gate, strict=True)
    ledger = RequestLedger(db)
    provider = MockHTTPProvider()
    provider.start_background()
    llm = GatewayLLM(base_url=provider.base_url, ledger=ledger, run_id="ipc-exh")
    ipc = tmp_path / "ipc"
    server = ModelIPCServer(ipc, llm)
    server.start()
    try:
        for rid in ("r1", "r2"):
            (ipc / "out" / f"{rid}.json").write_text(
                f'{{"id": "{rid}", "prompt": "p"}}', encoding="utf-8"
            )
        import time

        time.sleep(1.0)
        r1 = (ipc / "in" / "r1.json").read_text(encoding="utf-8") if (ipc / "in" / "r1.json").exists() else ""
        r2 = (ipc / "in" / "r2.json").read_text(encoding="utf-8") if (ipc / "in" / "r2.json").exists() else ""
        # first should succeed, second should fail-closed
        assert '"ok": true' in r1
        assert '"ok": false' in r2 or r2 == ""
    finally:
        server.stop()
        install_global_gate(None, strict=False)
        provider.shutdown()
        db.close()
