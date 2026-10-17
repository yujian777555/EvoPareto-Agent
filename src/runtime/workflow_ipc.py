"""Controlled model IPC for isolated Workflow execution (Task 4).

Problem:
  docker --network none blocks ALL TCP (so Workflow cannot reach any HTTP
  gateway), but generated Workflow code must still be able to run model
  inference under budget control.

Solution:
  a bind-mounted mailbox directory is the ONLY model channel.
    /ipc/out/<id>.json   Workflow -> host   (request)
    /ipc/in/<id>.json    host -> Workflow   (response)
  The host side drains requests through GatewayLLM (PhysicalBudgetGate +
  request_ledger). Container keeps --network none, no host env secrets, no
  docker.sock. CPU / memory / pids / timeout are capped by Docker flags.

This is an authorised host-model-service proxy: the mailbox is the control
boundary, not open network access.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# In-container client (embedded into the runner the container executes)
# ---------------------------------------------------------------------------
IN_CONTAINER_CLIENT = r'''
import json, os, time, uuid
from pathlib import Path

class ModelIPCClient:
    """Controlled model channel for isolated workflow code.

    Matches AFlow AsyncLLM call surface: `await self.llm(prompt)`.
    """
    def __init__(self, root="/ipc", timeout=15.0):
        self.root = Path(root)
        self.out = self.root / "out"
        self.inn = self.root / "in"
        self.timeout = timeout

    async def __call__(self, prompt, **kw):
        return self.complete(str(prompt))

    async def call_with_format(self, prompt, formatter=None):
        raw = self.complete(str(prompt))
        return {"modification": "ipc-mod", "graph": raw, "prompt": "INSTRUCTION = 'ipc'"}

    def get_usage_summary(self):
        return {"channel": "model-ipc-mailbox"}

    def complete(self, prompt: str, *, model: str = "deepseek-flash") -> str:
        rid = uuid.uuid4().hex
        req = self.out / f"{rid}.json"
        resp = self.inn / f"{rid}.json"
        req.write_text(json.dumps({"id": rid, "prompt": prompt, "model": model}), encoding="utf-8")
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if resp.exists():
                try:
                    data = json.loads(resp.read_text(encoding="utf-8"))
                except Exception:
                    time.sleep(0.05)
                    continue
                resp.unlink(missing_ok=True)
                if data.get("ok"):
                    return data.get("content", "")
                raise RuntimeError("MODEL_IPC_ERROR:" + str(data.get("error")))
            time.sleep(0.05)
        raise TimeoutError("model ipc timeout")
'''


class ModelIPCServer:
    """Host side of the mailbox. Runs GatewayLLM for every request."""

    def __init__(self, ipc_root: Path, llm: Any) -> None:
        self.root = Path(ipc_root)
        self.out = self.root / "out"
        self.inn = self.root / "in"
        self.out.mkdir(parents=True, exist_ok=True)
        self.inn.mkdir(parents=True, exist_ok=True)
        self.llm = llm
        self.processed: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            for req_path in sorted(self.out.glob("*.json")):
                try:
                    data = json.loads(req_path.read_text(encoding="utf-8"))
                except Exception:
                    req_path.unlink(missing_ok=True)
                    continue
                rid = data.get("id") or req_path.stem
                try:
                    content = self.llm._request(str(data.get("prompt", "")))
                    payload = {"ok": True, "content": content}
                except Exception as e:
                    payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
                (self.inn / f"{rid}.json").write_text(
                    json.dumps(payload), encoding="utf-8"
                )
                self.processed.append({"id": rid, "ok": payload["ok"]})
                req_path.unlink(missing_ok=True)
            time.sleep(0.02)


def run_workflow_code_isolated(
    graph_code: str,
    *,
    problem: str = "1+1",
    timeout: int = 20,
    memory_mb: int = 256,
    pids_limit: int = 64,
    cpus: float = 1.0,
    llm: Any = None,
) -> Dict[str, Any]:
    """Run generated Workflow in Docker with a controlled model mailbox.

    Isolation:
      --network none            (no TCP egress at all)
      --memory / --memory-swap  (RAM cap)
      --pids-limit              (fork bomb)
      --cpus                    (CPU cap)
      bind-mount /work + /ipc   (no docker.sock, no host env secrets)
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        work = td_path / "work"
        ipc = td_path / "ipc"
        work.mkdir()
        ipc.mkdir()
        (ipc / "out").mkdir()
        (ipc / "in").mkdir()

        server = None
        if llm is not None:
            server = ModelIPCServer(ipc, llm)
            server.start()

        (work / "graph.py").write_text(graph_code, encoding="utf-8")
        runner = (
            "import asyncio, json, sys, os\n"
            "sys.path.insert(0, '/work')\n"
            "sys.path.insert(0, '/ipc')\n"
            "from graph import Workflow\n"
            + IN_CONTAINER_CLIENT
            + "\n"
            "class Bound(Workflow):\n"
            "    def __init__(self):\n"
            "        super().__init__()\n"
            "        self.model = ModelIPCClient('/ipc')\n"
            "    async def __call__(self, problem):\n"
            "        return await super().__call__(problem)\n"
            "async def main():\n"
            "    w = Bound()\n"
            "    # expose controlled model handle if workflow wants it\n"
            "    if hasattr(w, 'model'):\n"
            "        pass\n"
            "    out = await w('1+1')\n"
            "    print(json.dumps({'ok': True, 'out': repr(out)[:300]}))\n"
            "asyncio.run(main())\n"
        )
        # simpler runner: just run the Workflow; pass ModelIPCClient via module
        (work / "model_ipc.py").write_text(IN_CONTAINER_CLIENT, encoding="utf-8")
        (work / "runner.py").write_text(
            "import asyncio, json, sys\n"
            "sys.path.insert(0, '/work')\n"
            "import model_ipc\n"
            "from graph import Workflow\n"
            "class Bound(Workflow):\n"
            "    model = None\n"
            "    async def __call__(self, problem):\n"
            "        # attach controlled model only; no raw sockets available\n"
            "        return await super().__call__(problem)\n"
            "async def main():\n"
            "    try:\n"
            "        w = Workflow()\n"
            "    except TypeError:\n"
            "        w = Workflow(None)\n"
            "    if hasattr(w, 'llm'):\n"
            "        w.llm = model_ipc.ModelIPCClient('/ipc')\n"
            "    out = await w('1+1')\n"
            "    print(json.dumps({'ok': True, 'out': repr(out)[:300]}))\n"
            "asyncio.run(main())\n",
            encoding="utf-8",
        )

        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", f"{memory_mb}m",
            "--memory-swap", f"{memory_mb}m",
            "--pids-limit", str(pids_limit),
            "--cpus", str(cpus),
            "-v", f"{work}:/work",
            "-v", f"{ipc}:/ipc",
            "-w", "/work",
            "-e", "PYTHONUNBUFFERED=1",
            # deliberately NO host secrets, NO proxy vars, NO docker.sock
            "python:3.10-slim",
            "python", "runner.py",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            if server:
                server.stop()
            return {"ok": False, "error": "TIMEOUT", "returncode": 124}
        finally:
            if server:
                server.stop()

        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-800:],
            "stderr": proc.stderr[-800:],
            "ipc_processed": getattr(server, "processed", []) if server else [],
        }


def run_workflow_with_model_probe(
    graph_code: str,
    *,
    llm: Any = None,
    **kw: Any,
) -> Dict[str, Any]:
    """Run a Workflow whose __call__ uses self.llm (wired to ModelIPCClient)."""
    return run_workflow_code_isolated(graph_code, llm=llm, **kw)
