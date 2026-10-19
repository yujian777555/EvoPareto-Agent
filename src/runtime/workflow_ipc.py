"""Isolated Workflow execution with secure model IPC (Stage 3.0-P1-R2A-R2).

Task 1: request-id validation, path containment, symlink refusal, atomic
        response handoff, size caps, duplicate refusal, trusted model only.
Task 4: the REAL task question is passed into the container (no "1+1" stub);
        task_id + question + gold answer travel together for offline scoring.
"""
from __future__ import annotations

import errno
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

REQUEST_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# Hard cap on the structured scoring payload. Exceeding it is a FAILURE,
# never a silent truncation.
MAX_STRUCTURED_RESULT_CHARS = 200_000
MAX_DIAG_EXCERPT_CHARS = 800
MAX_PIPE_BYTES = 4_000_000


def _run_bounded(cmd, *, timeout, max_bytes=MAX_PIPE_BYTES, cleanup_fn=None):
    """Bounded pipe reads + RELIABLE container cleanup via --cidfile."""
    import subprocess as _sp
    import threading as _th
    import tempfile as _tf
    import os as _os

    fd, cidfile = _tf.mkstemp(prefix="cid_", suffix=".txt")
    _os.close(fd)
    _os.unlink(cidfile)
    full_cmd = list(cmd)
    if full_cmd and full_cmd[0] == "docker":
        full_cmd = ["docker", "run", "--cidfile", cidfile] + full_cmd[2:]
    else:
        full_cmd = ["docker", "run", "--cidfile", cidfile] + full_cmd[1:]

    cleanup_status = {"container_id": None, "cleaned": False, "error": None}

    def _cleanup():
        cid = cleanup_status["container_id"]
        try:
            if cidfile and Path(cidfile).exists():
                cid = Path(cidfile).read_text().strip() or cid
        except Exception:
            pass
        cleanup_status["container_id"] = cid
        if not cid:
            cleanup_status["container_created"] = False
            cleanup_status["cleaned"] = True
            cleanup_status["error"] = "CONTAINER_NOT_CREATED"
            try:
                if cidfile and Path(cidfile).exists():
                    Path(cidfile).unlink()
            except Exception:
                pass
            if cleanup_fn:
                try:
                    cleanup_fn()
                except Exception:
                    pass
            return
        cleanup_status["container_created"] = True
        try:
            r = _sp.run(["docker", "rm", "-f", cid], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=15)
            out = (r.stdout or "") + (r.stderr or "")
            if r.returncode == 0:
                cleanup_status["cleaned"] = True
            elif "no such container" in out.lower():
                cleanup_status["cleaned"] = True
                cleanup_status["error"] = "ALREADY_REMOVED"
            else:
                cleanup_status["cleaned"] = False
                cleanup_status["error"] = f"DOCKER_RM_FAILED:{r.returncode}:{out[:120]}"
        except Exception as e:
            cleanup_status["cleaned"] = False
            cleanup_status["error"] = f"CLEANUP_EXCEPTION:{type(e).__name__}"
        finally:
            try:
                if cidfile and Path(cidfile).exists():
                    Path(cidfile).unlink()
            except Exception:
                pass
        if cleanup_fn:
            try:
                cleanup_fn()
            except Exception:
                pass

    try:
        proc = _sp.Popen(full_cmd, stdout=_sp.PIPE, stderr=_sp.PIPE, stdin=_sp.DEVNULL)
    except Exception as e:
        # startup failure: container never created; clean CID + run cleanup_fn
        cleanup_status["container_created"] = False
        cleanup_status["cleaned"] = True
        cleanup_status["error"] = f"POPEN_FAILED:{type(e).__name__}"
        try:
            if cidfile and Path(cidfile).exists():
                Path(cidfile).unlink()
        except Exception:
            pass
        if cleanup_fn:
            try:
                cleanup_fn()
            except Exception:
                pass
        return None, b"", b"", {"out": False, "err": False, "popen_failed": True}, cleanup_status
    out_buf = bytearray()
    err_buf = bytearray()
    overflow = {"out": False, "err": False}

    def _drain(fh, buf, key):
        try:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8", errors="replace")
                if len(buf) + len(chunk) > max_bytes:
                    buf.extend(chunk[: max_bytes - len(buf)])
                    overflow[key] = True
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    break
                buf.extend(chunk)
        except Exception:
            pass

    t_out = _th.Thread(target=_drain, args=(proc.stdout, out_buf, "out"), daemon=True)
    t_err = _th.Thread(target=_drain, args=(proc.stderr, err_buf, "err"), daemon=True)
    t_out.start()
    t_err.start()
    try:
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        overflow["timeout"] = True
    t_out.join(timeout=5)
    t_err.join(timeout=5)
    _cleanup()
    return proc, bytes(out_buf), bytes(err_buf), overflow, cleanup_status


MAX_REQUEST_BYTES = 256 * 1024
MAX_PROMPT_CHARS = 32_000
MAX_PENDING_REQUESTS = 64
MAX_RESPONSE_BYTES = 256 * 1024


class IPCSecurityError(RuntimeError):
    """Untrusted IPC input rejected. Never triggers a model call."""


class IPCDuplicateRequest(IPCSecurityError):
    pass


def validate_request_id(rid: Any) -> str:
    if not isinstance(rid, str):
        raise IPCSecurityError(f"NON_STRING_ID:{type(rid).__name__}")
    if not REQUEST_ID_RE.match(rid):
        raise IPCSecurityError(f"INVALID_ID:{rid[:80]!r}")
    if len(rid) != 32:
        raise IPCSecurityError(f"BAD_ID_LENGTH:{len(rid)}")
    return rid


def _safe_join(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name:
        raise IPCSecurityError("EMPTY_NAME")
    if "/" in name or "\\" in name:
        raise IPCSecurityError(f"PATH_SEPARATOR:{name[:40]!r}")
    if name.startswith(".") or ".." in name:
        raise IPCSecurityError(f"TRAVERSAL:{name[:40]!r}")
    if re.match(r"^[A-Za-z]:", name) or name.startswith("\\\\"):
        raise IPCSecurityError(f"WINDOWS_PATH:{name[:40]!r}")
    if os.path.isabs(name):
        raise IPCSecurityError(f"ABSOLUTE_PATH:{name[:40]!r}")
    root_l = os.path.abspath(str(root))
    candidate = os.path.abspath(os.path.join(root_l, name))
    if candidate != root_l and not candidate.startswith(root_l + os.sep):
        raise IPCSecurityError(f"ESCAPE:{name[:40]!r}")
    return Path(candidate)


def _read_json_bounded(path: Path, max_bytes: int) -> Dict[str, Any]:
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as e:
        if e.errno in (errno.ELOOP, errno.EACCES):
            raise IPCSecurityError(f"SYMLINK_REQUEST:{path.name}") from e
        raise
    try:
        st = os.fstat(fd)
        if st.st_size > max_bytes:
            raise IPCSecurityError(f"OVERSIZED_REQUEST:{st.st_size}")
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            data = json.loads(fh.read())
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    if not isinstance(data, dict):
        raise IPCSecurityError("NON_OBJECT_REQUEST")
    return data


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_RESPONSE_BYTES:
        payload = {"ok": False, "error": "RESPONSE_TOO_LARGE"}
        body = json.dumps(payload).encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_EXCL", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError as e:
        raise IPCSecurityError(f"RESPONSE_EXISTS:{path.name}") from e
    except OSError as e:
        raise IPCSecurityError(f"RESPONSE_OPEN_FAIL:{path.name}:{e.errno}") from e
    with os.fdopen(fd, "wb") as fh:
        fh.write(body)
        fh.flush()
        os.fsync(fh.fileno())


def _unlink_quiet(path: Path) -> None:
    try:
        os.unlink(str(path))
    except OSError:
        pass


# ---------------------------------------------------------------------------
# In-container client
# ---------------------------------------------------------------------------
IN_CONTAINER_CLIENT = r'''
import json, os, time, uuid
from pathlib import Path

class ModelIPCClient:
    """Controlled model channel for isolated workflow code."""
    def __init__(self, root="/ipc", timeout=15.0):
        self.root = Path(root)
        self.out = self.root / "out"
        self.inn = self.root / "in"
        self.timeout = timeout

    async def __call__(self, prompt, **kw):
        return self.complete(str(prompt))

    async def call_with_format(self, prompt, formatter=None):
        raw = self.complete(str(prompt))
        # shape matches AFlow operator output (has 'response' for graph.py)
        return {
            "response": raw,
            "modification": "ipc-mod",
            "graph": raw,
            "prompt": "INSTRUCTION = 'ipc'",
        }

    def get_usage_summary(self):
        return {"channel": "model-ipc-mailbox", "total_cost": 0.0, "total_input_tokens": 0, "total_output_tokens": 0}

    def complete(self, prompt: str, *, model: str = "deepseek-flash") -> str:
        rid = uuid.uuid4().hex
        req = self.out / f"{rid}.json"
        resp = self.inn / f"{rid}.json"
        body = json.dumps({"id": rid, "prompt": str(prompt)[:32000]})
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(str(req), flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if resp.exists():
                try:
                    data = json.loads(resp.read_text(encoding="utf-8"))
                except Exception:
                    time.sleep(0.05)
                    continue
                try:
                    os.unlink(str(resp))
                except OSError:
                    pass
                if data.get("ok"):
                    return data.get("content", "")
                raise RuntimeError("MODEL_IPC_ERROR:" + str(data.get("error")))
            time.sleep(0.05)
        raise TimeoutError("model ipc timeout")
'''


class ModelIPCServer:
    """Host side of the mailbox. Every request is validated before any model call."""

    def __init__(self, ipc_root: Path, llm: Any, *, trusted_model: str = "deepseek-flash") -> None:
        self.root = Path(ipc_root)
        self.out = self.root / "out"
        self.inn = self.root / "in"
        self.out.mkdir(parents=True, exist_ok=True)
        self.inn.mkdir(parents=True, exist_ok=True)
        self.llm = llm
        self.trusted_model = trusted_model
        self.processed: List[Dict[str, Any]] = []
        self.security_events: List[Dict[str, Any]] = []
        self._seen: Set[str] = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _event(self, kind: str, detail: str) -> None:
        with self._lock:
            self.security_events.append({"kind": kind, "detail": detail[:200]})

    def _handle_one(self, req_path: Path) -> None:
        filename = req_path.name
        try:
            rid = validate_request_id(filename[:-5] if filename.endswith(".json") else filename)
        except IPCSecurityError as e:
            self._event("REJECT_ID", str(e))
            _unlink_quiet(req_path)
            return

        try:
            data = _read_json_bounded(req_path, MAX_REQUEST_BYTES)
        except IPCSecurityError as e:
            self._event("REJECT_READ", str(e))
            _unlink_quiet(req_path)
            return

        json_id = data.get("id")
        if json_id is not None:
            try:
                json_id = validate_request_id(json_id)
            except IPCSecurityError as e:
                self._event("REJECT_JSON_ID", str(e))
                _unlink_quiet(req_path)
                return
            if json_id != rid:
                self._event("REJECT_ID_MISMATCH", f"{json_id}!={rid}")
                _unlink_quiet(req_path)
                return

        if "model" in data and data["model"] not in (None, self.trusted_model):
            self._event("REJECT_UNAUTHORIZED_MODEL", str(data.get("model"))[:80])
            _unlink_quiet(req_path)
            return

        prompt = data.get("prompt")
        if not isinstance(prompt, str):
            self._event("REJECT_PROMPT_TYPE", type(prompt).__name__)
            _unlink_quiet(req_path)
            return
        if len(prompt) > MAX_PROMPT_CHARS:
            self._event("REJECT_OVERSIZED_PROMPT", str(len(prompt)))
            _unlink_quiet(req_path)
            return

        with self._lock:
            if rid in self._seen:
                self._event("REJECT_DUPLICATE", rid)
                _unlink_quiet(req_path)
                return
            if len(self._seen) >= MAX_PENDING_REQUESTS:
                self._event("REJECT_BACKLOG", rid)
                _unlink_quiet(req_path)
                return
            self._seen.add(rid)

        resp_path = _safe_join(self.inn, f"{rid}.json")
        try:
            content = self.llm._request(prompt)
            payload: Dict[str, Any] = {"ok": True, "content": content}
        except Exception as e:
            payload = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        try:
            _write_json_atomic(resp_path, payload)
        except IPCSecurityError as e:
            self._event("REJECT_RESPONSE_WRITE", str(e))
        self.processed.append({"id": rid, "ok": payload["ok"]})
        _unlink_quiet(req_path)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                entries = sorted(self.out.glob("*.json"))
            except Exception:
                entries = []
            for req_path in entries:
                if self._stop.is_set():
                    return
                try:
                    self._handle_one(req_path)
                except Exception as e:
                    self._event("SERVER_ERROR", f"{type(e).__name__}: {e}")
            time.sleep(0.02)


# ---------------------------------------------------------------------------
# Isolated runner — Task 4: real task question, not "1+1"
# ---------------------------------------------------------------------------

def build_runner_script(task_question: str, task_id: str) -> str:
    """Runner embeds the REAL question via a JSON sidecar (no shell quoting risk)."""
    return (
        "import asyncio, json, sys\n"
        "sys.path.insert(0, '/work')\n"
        "import model_ipc\n"
        "try:\n"
        "    import scripts.async_llm as _al\n"
        "    _al.create_llm_instance = lambda cfg=None: model_ipc.ModelIPCClient('/ipc')\n"
        "except Exception:\n"
        "    pass\n"
        "import importlib, sys\n"
        "import graph as _g\n"
        "# Bind INSTRUCTION from prompt.py into the graph module namespace when\n"
        "# the real generated graph references a bare INSTRUCTION name.\n"
        "# This is a loader binding — the graph source itself is never rewritten.\n"
        "if not hasattr(_g, 'INSTRUCTION'):\n"
        "    for cand in (\n"
        "        'workspace.GSM8K.workflows.round_2.prompt',\n"
        "        'workspace.GSM8K.workflows.round_1.prompt',\n"
        "        'workspace.GSM8K.workflows.round_3.prompt',\n"
        "        'prompt',\n"
        "    ):\n"
        "        try:\n"
        "            _m = importlib.import_module(cand)\n"
        "            if hasattr(_m, 'INSTRUCTION'):\n"
        "                _g.INSTRUCTION = _m.INSTRUCTION\n"
        "                break\n"
        "        except Exception:\n"
        "            continue\n"
        "Workflow = _g.Workflow\n"
        "task = json.load(open('/work/task.json', encoding='utf-8'))\n"
        "async def main():\n"
        "    w = None\n"
        "    dummy_cfg = {'model': 'mock', 'api_key': 'x', 'base_url': 'http://127.0.0.1:1/v1'}\n"
        "    dummy_ds = type('D', (), {'name': 'GSM8K'})()\n"
        "    for ctor in (\n"
        "        lambda: Workflow(),\n"
        "        lambda: Workflow(None),\n"
        "        lambda: Workflow('w', dummy_cfg, dummy_ds),\n"
        "        lambda: Workflow('w', None, dummy_ds),\n"
        "        lambda: Workflow('w', dummy_cfg, None),\n"
        "    ):\n"
        "        try:\n"
        "            w = ctor()\n"
        "            break\n"
        "        except Exception:\n"
        "            continue\n"
        "    if w is None:\n"
        "        raise TypeError('Workflow constructor not compatible')\n"
        "    if hasattr(w, 'llm'):\n"
        "        w.llm = model_ipc.ModelIPCClient('/ipc')\n"
        "    out = await w(task['question'])\n"
        "    if isinstance(out, (tuple, list)) and len(out) >= 2:\n"
        "        answer_text = str(out[0]); cost_meta = out[1]; out_kind = 'tuple'\n"
        "    else:\n"
        "        answer_text = str(out); cost_meta = None; out_kind = 'plain'\n"
        "    print(json.dumps({'ok': True, 'task_id': task.get('task_id'),"
        " 'answer_text': answer_text, 'answer_len': len(answer_text),"
        " 'cost_meta': (repr(cost_meta) if cost_meta is not None else None),"
        " 'out_kind': out_kind, 'question_len': len(task.get('question','')),"
        " 'task_keys': sorted(task.keys())}, ensure_ascii=False))\n"
        "asyncio.run(main())\n"
    )


def run_workflow_code_isolated(
    graph_code: str,
    *,
    problem: str = "",
    task_id: str = "adhoc",
    gold_answer: Optional[str] = None,
    timeout: int = 20,
    memory_mb: int = 256,
    pids_limit: int = 64,
    cpus: float = 1.0,
    llm: Any = None,
    extra_modules: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Run generated Workflow in Docker with a controlled model mailbox.

    The REAL `problem` (GSM8K question) is written to /work/task.json and the
    runner passes it to the Workflow. Gold answer never crosses the boundary.

    `extra_modules` maps module dotted-names to source text so official graph
    imports (e.g. workspace...operator) resolve inside the container.
    """
    if not problem:
        raise ValueError("problem (real task question) is required")

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
        (work / "model_ipc.py").write_text(IN_CONTAINER_CLIENT, encoding="utf-8")
        # ship optional dependency modules (official AFlow template packages)
        if extra_modules:
            has_child = set()
            for dotted in extra_modules:
                parts = dotted.split(".")
                for i in range(1, len(parts)):
                    has_child.add(".".join(parts[:i]))
            for dotted, src in extra_modules.items():
                parts = dotted.split(".")
                dest_dir = work.joinpath(*parts[:-1])
                dest_dir.mkdir(parents=True, exist_ok=True)
                cur = work
                for part in parts[:-1]:
                    cur = cur / part
                    (cur / "__init__.py").touch()
                if dotted in has_child:
                    pkg_dir = work.joinpath(*parts)
                    pkg_dir.mkdir(parents=True, exist_ok=True)
                    (pkg_dir / "__init__.py").write_text(src, encoding="utf-8")
                else:
                    (dest_dir / (parts[-1] + ".py")).write_text(src, encoding="utf-8")
        # SECURITY: container-visible task payload carries ONLY id + question.
        # Gold answer stays on the host for the trusted scorer — never in
        # /work/task.json, never in the prompt, never over IPC.
        (work / "task.json").write_text(
            json.dumps({
                "task_id": task_id,
                "question": problem,
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        if extra_modules:
            # ensure every parent package is importable
            for dotted in extra_modules:
                parts = dotted.split(".")
                for i in range(len(parts)):
                    pkg = work.joinpath(*parts[: i + 1])
                    if pkg.is_dir():
                        (pkg / "__init__.py").touch()
        (work / "runner.py").write_text(build_runner_script(problem, task_id), encoding="utf-8")

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
            "python:3.10-slim",
            "python", "runner.py",
        ]
        try:
            proc, out_bytes, err_bytes, overflow, cleanup_status = _run_bounded(cmd, timeout=timeout + 15)
        except subprocess.TimeoutExpired:
            if server:
                server.stop()
            return {
                "ok": False, "error": "TIMEOUT", "returncode": 124,
                "task_id": task_id, "security_events": [],
                "ipc_processed": [],
                "docker_cleanup": {"error": "TIMEOUT_PATH"},
            }
        finally:
            if server:
                server.stop()

        # ---- Task A: parse the FULL stdout before any excerpting ----
        full_stdout = out_bytes.decode("utf-8", errors="replace")
        full_stderr = err_bytes.decode("utf-8", errors="replace")
        if overflow.get("out") or overflow.get("err") or overflow.get("timeout"):
            return {
                "ok": False,
                "error": "PIPE_OVERFLOW",
                "returncode": proc.returncode if proc.returncode is not None else -1,
                "task_id": task_id,
                "answer_text": None, "answer_len": 0, "answer_sha256": None,
                "cost_meta": None, "out_kind": None,
                "stdout_excerpt": full_stdout[-MAX_DIAG_EXCERPT_CHARS:],
                "stderr_excerpt": full_stderr[-MAX_DIAG_EXCERPT_CHARS:],
                "question_len": len(problem),
                "ipc_processed": [], "security_events": [],
                "docker_cleanup": cleanup_status,
            }
        if len(full_stdout) > MAX_STRUCTURED_RESULT_CHARS:
            return {
                "ok": False,
                "error": "STRUCTURED_RESULT_TOO_LARGE",
                "returncode": proc.returncode,
                "task_id": task_id,
                "answer_text": None,
                "answer_len": len(full_stdout),
                "answer_sha256": None,
                "cost_meta": None,
                "out_kind": None,
                "stdout_excerpt": full_stdout[-MAX_DIAG_EXCERPT_CHARS:],
                "stderr_excerpt": full_stderr[-MAX_DIAG_EXCERPT_CHARS:],
                "question_len": len(problem),
                "ipc_processed": getattr(server, "processed", []) if server else [],
                "security_events": getattr(server, "security_events", []) if server else [],
                "docker_cleanup": cleanup_status,
            }

        structured = None
        parse_status = "NO_JSON_FOUND"
        # the runner prints one JSON object; find the first '{' and parse from there
        json_start = full_stdout.find("{")
        if json_start >= 0:
            try:
                structured = json.loads(full_stdout[json_start:])
                parse_status = "PARSED"
            except Exception as e:
                structured = None
                parse_status = f"JSON_PARSE_FAILED:{type(e).__name__}"

        if structured is None:
            # JSON parse failure must REFUSE scoring, not fall back to log scraping
            return {
                "ok": False,
                "error": parse_status,
                "returncode": proc.returncode,
                "task_id": task_id,
                "answer_text": None,
                "answer_len": 0,
                "answer_sha256": None,
                "cost_meta": None,
                "out_kind": None,
                "stdout_excerpt": full_stdout[-MAX_DIAG_EXCERPT_CHARS:],
                "stderr_excerpt": full_stderr[-MAX_DIAG_EXCERPT_CHARS:],
                "question_len": len(problem),
                "ipc_processed": getattr(server, "processed", []) if server else [],
                "security_events": getattr(server, "security_events", []) if server else [],
                "docker_cleanup": cleanup_status,
            }

        answer_text = structured.get("answer_text")
        answer_len = structured.get("answer_len")
        if answer_text is None:
            # legacy field fallback ONLY inside the structured object
            answer_text = structured.get("out")
            answer_len = len(answer_text) if answer_text is not None else 0

        return {
            "ok": proc.returncode == 0 and answer_text is not None and (cleanup_status.get("cleaned") is True or cleanup_status.get("container_created") is False),
            "returncode": proc.returncode,
            # full structured result (never truncated for scoring)
            "answer_text": answer_text,
            "answer_len": answer_len if answer_len is not None else (len(answer_text or "")),
            "answer_sha256": __import__("hashlib").sha256(
                (answer_text or "").encode("utf-8", errors="replace")
            ).hexdigest() if answer_text is not None else None,
            "cost_meta": structured.get("cost_meta"),
            "out_kind": structured.get("out_kind"),
            "task_id": structured.get("task_id") or task_id,
            "task_keys": structured.get("task_keys"),
            "question_len": structured.get("question_len", len(problem)),
            "gold_answer_host_side": gold_answer,   # trusted scorer only
            # independent diagnostics (excerpted; NEVER used for scoring)
            "stdout_excerpt": full_stdout[-MAX_DIAG_EXCERPT_CHARS:],
            "stderr_excerpt": full_stderr[-MAX_DIAG_EXCERPT_CHARS:],
            "ipc_processed": getattr(server, "processed", []) if server else [],
            "security_events": getattr(server, "security_events", []) if server else [],
            "parse_status": parse_status,
            "docker_cleanup": cleanup_status,
        }


def run_workflow_with_model_probe(graph_code: str, *, llm: Any = None, **kw: Any) -> Dict[str, Any]:
    return run_workflow_code_isolated(graph_code, llm=llm, **kw)
