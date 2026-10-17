"""Provider Gateway for AFlow LLM traffic (Stage 3.0-P1-R2A-R1 Task 2).

Wires the real AFlow call chains through PhysicalBudgetGate and a Mock HTTP
provider so that every physical request is reserved, sent, and settled:

  AFlow Optimizer  -> optimize_llm (GatewayLLM) -> HTTP POST /v1/chat/completions
  AFlow Workflow   -> Operator.llm (GatewayLLM)  -> HTTP POST /v1/chat/completions

Design rules:
  - pre_send_ticket() BEFORE any socket send (fail-closed, no bypass)
  - append-only request_ledger row per physical request (never meta-overwrite)
  - missing usage / unknown price / timeout / partial response -> settle failed
    and, for untrusted cost, mark billing blocked (fail-closed)
  - generated workflow code must only reach the model through this interface
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.runtime.http_budget import (
    BillingBlocked,
    BudgetDB,
    BudgetExceeded,
    GateRequired,
    PhysicalBudgetGate,
    install_global_gate,
    pre_send_ticket,
    settle_ticket,
)

# ---------------------------------------------------------------------------
# Pricing (verified against api-docs.deepseek.com 2026-10-16)
# ---------------------------------------------------------------------------
PRICE_TABLE_USD_PER_1M: Dict[str, Dict[str, float]] = {
    "deepseek-flash": {
        "input_cache_miss_peak": 0.30,
        "input_cache_miss_offpeak": 0.15,
        "input_cache_hit_peak": 0.006,
        "input_cache_hit_offpeak": 0.003,
        "output_peak": 1.20,
        "output_offpeak": 0.60,
    },
    "deepseek-v4-pro": {
        "input_cache_miss_peak": 1.32,
        "input_cache_miss_offpeak": 0.66,
        "input_cache_hit_peak": 0.044,
        "input_cache_hit_offpeak": 0.022,
        "output_peak": 3.96,
        "output_offpeak": 1.98,
    },
}

PRICE_VERIFIED_AT = "2026-10-16"
PRICE_SOURCE = "https://api-docs.deepseek.com/quick_start/pricing"


class UnknownModelPrice(RuntimeError):
    pass


class UsageMissing(RuntimeError):
    pass


class PartialResponse(RuntimeError):
    pass


class GatewayTimeout(RuntimeError):
    pass


def estimate_cost(model: str, tokens_in: int, tokens_out: int, *, peak: bool = True) -> float:
    """Conservative cost: peak cache-miss by default. Unknown model -> fail-closed."""
    prices = PRICE_TABLE_USD_PER_1M.get(model)
    if prices is None:
        raise UnknownModelPrice(model)
    in_key = "input_cache_miss_peak" if peak else "input_cache_miss_offpeak"
    out_key = "output_peak" if peak else "output_offpeak"
    return (tokens_in / 1_000_000.0) * prices[in_key] + (tokens_out / 1_000_000.0) * prices[out_key]


class InputTokenCapExceeded(RuntimeError):
    pass


class OutputTokenCapExceeded(RuntimeError):
    pass


def conservative_input_tokens(prompt: str) -> int:
    """Upper bound on input tokens: 1 token per char + framing headroom.

    Never under-estimates for CJK / punctuation-heavy text.
    """
    return len(prompt) + 8


def worst_case_cost(model: str, max_in: int, max_out: int) -> float:
    """Reservation must cover the full peak cache-miss bill for the token bounds."""
    return estimate_cost(model, max_in, max_out, peak=True)


class StructuredOutputError(RuntimeError):
    """Model returned unusable structure. Never synthesised into a fake mutation."""


# ---------------------------------------------------------------------------
# Append-only per-request ledger (NOT a single meta key)
# ---------------------------------------------------------------------------

class RequestLedger:
    """One row per physical request. History is never overwritten."""

    def __init__(self, db: BudgetDB) -> None:
        self.db = db
        with db._lock:
            db._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS request_ledger (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    run_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    logical_request_id TEXT NOT NULL,
                    physical_request_id TEXT NOT NULL,
                    ticket_id TEXT NOT NULL,
                    max_input_tokens INTEGER NOT NULL,
                    max_output_tokens INTEGER NOT NULL,
                    reserved_cost REAL NOT NULL,
                    reported_tokens_in INTEGER,
                    reported_tokens_out INTEGER,
                    observed_cost REAL,
                    cumulative_cost REAL NOT NULL,
                    request_status TEXT NOT NULL,
                    error_kind TEXT,
                    http_status INTEGER
                )
                """
            )
            db._conn.commit()
        self._cum_lock = threading.Lock()

    def append(
        self,
        *,
        run_id: str,
        provider: str,
        model: str,
        logical_request_id: str,
        physical_request_id: str,
        ticket_id: str,
        max_input_tokens: int,
        max_output_tokens: int,
        reserved_cost: float,
        reported_tokens_in: Optional[int],
        reported_tokens_out: Optional[int],
        observed_cost: Optional[float],
        request_status: str,
        error_kind: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> int:
        snap = self.db.snapshot()
        with self.db._lock:
            cur = self.db._conn.execute(
                """
                INSERT INTO request_ledger (
                    ts, run_id, provider, model, logical_request_id,
                    physical_request_id, ticket_id, max_input_tokens,
                    max_output_tokens, reserved_cost, reported_tokens_in,
                    reported_tokens_out, observed_cost, cumulative_cost,
                    request_status, error_kind, http_status
                ) VALUES (strftime('%s','now') + 0.0,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_id, provider, model, logical_request_id,
                    physical_request_id, ticket_id, max_input_tokens,
                    max_output_tokens, reserved_cost, reported_tokens_in,
                    reported_tokens_out, observed_cost,
                    float(snap["spent_cost_usd"]), request_status,
                    error_kind, http_status,
                ),
            )
            self.db._conn.commit()
            return int(cur.lastrowid)

    def rows(self) -> List[Dict[str, Any]]:
        with self.db._lock:
            cur = self.db._conn.execute("SELECT * FROM request_ledger ORDER BY seq")
            return [dict(r) for r in cur.fetchall()]

    def count(self) -> int:
        with self.db._lock:
            return int(self.db._conn.execute("SELECT COUNT(*) AS c FROM request_ledger").fetchone()["c"])


# ---------------------------------------------------------------------------
# Mock HTTP Provider (OpenAI-compatible chat completions)
# ---------------------------------------------------------------------------

class MockHTTPProvider(ThreadingHTTPServer):
    """Local OpenAI-compatible endpoint. Can simulate failure modes."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, *, scenario: str = "ok") -> None:
        self.scenario = scenario  # ok | missing_usage | partial | timeout | http_500 | http_429
        self.requests_seen: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: D102
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    body = {}
                with provider._lock:
                    provider.requests_seen.append({"path": self.path, "body": body})

                scenario = provider.scenario
                if scenario == "http_429":
                    self.send_response(429)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"rate limited"}}')
                    return
                if scenario == "http_500":
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"server error"}}')
                    return
                if scenario == "timeout":
                    time.sleep(30)
                if scenario == "partial":
                    payload = b'{"id":"x","choices":[{"message":{"role":"assistant"'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                n_in = max(1, len(str(body.get("messages", ""))) // 4)
                n_out = 16
                content = "mock-gateway-response"
                usage = {"prompt_tokens": n_in, "completion_tokens": n_out, "total_tokens": n_in + n_out}
                if scenario == "missing_usage":
                    usage = None
                resp = {
                    "id": "chatcmpl-" + uuid.uuid4().hex[:10],
                    "object": "chat.completion",
                    "model": body.get("model", "deepseek-flash"),
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }],
                }
                if usage is not None:
                    resp["usage"] = usage
                data = json.dumps(resp).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        super().__init__((host, port), Handler)

    @property
    def base_url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}/v1"

    def start_background(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t


# ---------------------------------------------------------------------------
# GatewayLLM — drop-in for AFlow AsyncLLM (same call surface)
# ---------------------------------------------------------------------------

class GatewayLLM:
    """Budget-gated LLM client matching AFlow's AsyncLLM interface.

    Sync implementation is fine for the offline pilot harness; AFlow awaits it
    from asyncio so we expose __call__ as a coroutine-compatible callable.
    """

    def __init__(
        self,
        *,
        model: str = "deepseek-flash",
        base_url: str,
        api_key: str = "gateway-key",
        ledger: RequestLedger,
        run_id: str = "r2a-r1",
        max_input_tokens: int = 2000,
        max_output_tokens: int = 500,
        timeout: float = 10.0,
        logical_request_prefix: str = "req",
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.ledger = ledger
        self.run_id = run_id
        self.max_input_tokens = max_input_tokens
        self.max_output_tokens = max_output_tokens
        self.timeout = timeout
        self.logical_request_prefix = logical_request_prefix
        self._logical_seq = 0
        self._logical_lock = threading.Lock()

    # AFlow calls llm(prompt) and llm.call_with_format(prompt, formatter)
    async def __call__(self, prompt: str, **kw: Any) -> str:
        return self._request(prompt)

    async def call_with_format(self, prompt: str, formatter: Any = None) -> Dict[str, Any]:
        """Structured modification parse. FAIL-CLOSED: never synthesise a mutation.

        AFlow-compatible XML tags: <modification>...</modification>
        <graph>...</graph> <prompt>...</prompt>. Invalid output raises
        StructuredOutputError so the caller can retry (budgeted) or discard
        the candidate — it must not invent a valid-looking modification.
        """
        raw = self._request(prompt)
        if formatter is not None:
            try:
                ok, parsed = formatter.validate_response(raw)
                if ok and isinstance(parsed, dict):
                    if not all(k in parsed for k in ("modification", "graph", "prompt")):
                        raise StructuredOutputError("MISSING_REQUIRED_FIELD")
                    return parsed
            except StructuredOutputError:
                raise
            except Exception as e:
                raise StructuredOutputError(f"FORMATTER_REJECTED:{type(e).__name__}") from e
        # XML-style parse (AFlow official formatter shape)
        import re as _re

        def _tag(name: str) -> Optional[str]:
            pat = r"<" + name + r">([\s\S]*?)</" + name + r">"
            m = _re.search(pat, raw or "")
            return m.group(1).strip() if m else None

        modification = _tag("modification")
        graph = _tag("graph")
        prompt_txt = _tag("prompt")
        if modification is None:
            raise StructuredOutputError("MISSING_MODIFICATION")
        if graph is None:
            raise StructuredOutputError("MISSING_GRAPH")
        if prompt_txt is None:
            raise StructuredOutputError("MISSING_PROMPT")
        if "class Workflow" not in graph:
            raise StructuredOutputError("MISSING_WORKFLOW_CLASS")
        try:
            compile(graph, "<graph>", "exec")
        except SyntaxError as e:
            raise StructuredOutputError(f"INVALID_PYTHON:{e.msg}") from e
        return {"modification": modification, "graph": graph, "prompt": prompt_txt}

    def get_usage_summary(self) -> Dict[str, Any]:
        rows = self.ledger.rows()
        return {
            "n_requests": len(rows),
            "spent_cost_usd": sum(r["observed_cost"] or 0.0 for r in rows),
            "tokens_in": sum(r["reported_tokens_in"] or 0 for r in rows),
            "tokens_out": sum(r["reported_tokens_out"] or 0 for r in rows),
        }

    # ---- core path: reserve -> HTTP -> settle, fail-closed ----
    def _next_logical_id(self) -> str:
        with self._logical_lock:
            self._logical_seq += 1
            return f"{self.logical_request_prefix}-{self._logical_seq}"

    def _request(self, prompt: str) -> str:
        """VALIDATE -> RESERVE -> SEND -> RECONCILE -> COMMIT.

        Reservation covers the conservative MAXIMUM cost for the token bounds,
        not a flat low fee. Uncertain billing after a physical send never
        settles at $0-and-continue; it blocks persistently.
        """


        logical_id = self._next_logical_id()
        physical_id = uuid.uuid4().hex

        # --- VALIDATE request ---
        if not isinstance(prompt, str):
            raise InputTokenCapExceeded("PROMPT_NOT_STRING")
        est_in = conservative_input_tokens(prompt)
        if est_in > self.max_input_tokens:
            raise InputTokenCapExceeded(
                f"estimated input tokens {est_in} > per-request cap {self.max_input_tokens}"
            )
        if self.max_output_tokens <= 0:
            raise OutputTokenCapExceeded("max_output_tokens must be positive")

        # --- VALIDATE model / price ---
        # Reservation covers THIS request's conservative maximum:
        #   input  = upper bound for this prompt
        #   output = full per-request output cap (we cannot know less)
        reserve_cost = worst_case_cost(self.model, est_in, self.max_output_tokens)

        # --- RESERVE request slot + token budget + worst-case cost ---
        ticket = pre_send_ticket(
            res_tokens_in=est_in,
            res_tokens_out=self.max_output_tokens,
            res_cost=reserve_cost,
        )

        http_status: Optional[int] = None
        error_kind: Optional[str] = None
        tokens_in: Optional[int] = None
        tokens_out: Optional[int] = None
        observed: Optional[float] = None
        content: str = ""
        sent = False
        try:
            content, http_status, tokens_in, tokens_out = self._http_chat(prompt)
            sent = True
            # --- RECONCILE trusted usage ---
            if tokens_in is None or tokens_out is None:
                raise UsageMissing("usage tokens missing after 200 response")
            if tokens_in > self.max_input_tokens or tokens_out > self.max_output_tokens:
                # provider returned more than we authorised — persist block
                raise UsageMissing(
                    f"USAGE_EXCEEDS_CAP in={tokens_in} out={tokens_out}"
                )
            observed = estimate_cost(self.model, tokens_in, tokens_out, peak=True)
            if observed > reserve_cost * 1.05 + 1e-9:
                # should be impossible under peak pricing; fail closed
                raise UsageMissing(f"COST_EXCEEDS_RESERVE {observed}>{reserve_cost}")
        except UnknownModelPrice as e:
            error_kind = "UNKNOWN_MODEL_PRICE"
            settle_ticket(ticket, success=False, actual_cost=reserve_cost)
            self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            self.ledger.db.mark_billing_blocked(str(e), ticket_id=ticket)
            raise
        except (UsageMissing, InputTokenCapExceeded, OutputTokenCapExceeded) as e:
            error_kind = type(e).__name__.upper() if not isinstance(e, UsageMissing) else "MISSING_USAGE"
            if isinstance(e, UsageMissing):
                error_kind = "MISSING_USAGE"
            settle_ticket(ticket, success=False, actual_cost=reserve_cost)
            self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            try:
                self.ledger.db.mark_billing_blocked(str(e), ticket_id=ticket)
            except Exception:
                pass
            raise
        except PartialResponse as e:
            error_kind = "PARTIAL_RESPONSE"
            # physical send may have been billed — occupy worst-case, then block
            if sent:
                self.ledger.db.settle_unknown_and_block(ticket, reason=f"PARTIAL_RESPONSE:{e}", tokens_in=0, tokens_out=0)
            else:
                settle_ticket(ticket, success=False, actual_cost=reserve_cost)
            self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            raise
        except (GatewayTimeout, TimeoutError) as e:
            error_kind = "TIMEOUT"
            # request may have been processed by the provider — unknown billing
            self.ledger.db.settle_unknown_and_block(ticket, reason=f"TIMEOUT:{e}", tokens_in=0, tokens_out=0)
            self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            raise
        except OSError as e:
            error_kind = f"OS:{type(e).__name__}"
            # connection reset / refused AFTER or DURING send => uncertain billing
            self.ledger.db.settle_unknown_and_block(ticket, reason=f"{error_kind}:{e}", tokens_in=0, tokens_out=0)
            self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            raise
        except Exception as e:
            error_kind = type(e).__name__
            msg = str(e)
            # HTTP 429/500/5xx or any post-send failure => billing is uncertain
            uncertain = sent or msg.startswith("HTTP_") or "HTTPError" in error_kind
            if uncertain:
                self.ledger.db.settle_unknown_and_block(ticket, reason=f"{error_kind}:{msg}", tokens_in=0, tokens_out=0)
                self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "fail_closed")
            else:
                settle_ticket(ticket, success=False, actual_cost=reserve_cost)
                self._ledger_fail(logical_id, physical_id, ticket, reserve_cost, error_kind, "failed")
            raise

        # --- COMMIT ledger (cost known, trusted) ---
        settle_ticket(
            ticket, success=True, actual_cost=float(observed or reserve_cost),
            tokens_in=tokens_in or 0, tokens_out=tokens_out or 0,
        )
        self.ledger.append(
            run_id=self.run_id, provider="mock-http", model=self.model,
            logical_request_id=logical_id, physical_request_id=physical_id,
            ticket_id=ticket, max_input_tokens=self.max_input_tokens,
            max_output_tokens=self.max_output_tokens,
            reserved_cost=float(reserve_cost),
            reported_tokens_in=tokens_in, reported_tokens_out=tokens_out,
            observed_cost=float(observed or reserve_cost),
            request_status="settled_ok", http_status=http_status,
        )
        return content

    def _ledger_fail(self, logical_id, physical_id, ticket, reserve_cost, error_kind, status):
        self.ledger.append(
            run_id=self.run_id, provider="mock-http", model=self.model,
            logical_request_id=logical_id, physical_request_id=physical_id,
            ticket_id=ticket, max_input_tokens=self.max_input_tokens,
            max_output_tokens=self.max_output_tokens, reserved_cost=float(reserve_cost),
            reported_tokens_in=None, reported_tokens_out=None, observed_cost=None,
            request_status=status, error_kind=error_kind,
        )

    def _http_chat(self, prompt: str) -> Tuple[str, int, int, int]:
        import urllib.error
        import urllib.request

        # DeepSeek physical requests must bypass the system/global proxy and go
        # direct to the official API (Task 3 proxy policy).
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = f"{self.base_url}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.max_output_tokens,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with opener.open(req, timeout=self.timeout) as resp:
                http_status = int(resp.status)
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body = e.read() if hasattr(e, "read") else b""
            raise RuntimeError(f"HTTP_{e.code}:{body[:200]}") from e
        except TimeoutError as e:
            raise GatewayTimeout(str(e)) from e
        except OSError as e:
            if "timed out" in str(e).lower():
                raise GatewayTimeout(str(e)) from e
            raise

        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise PartialResponse(f"unparseable body: {raw[:80]!r}") from e
        if "choices" not in data or not data["choices"]:
            raise PartialResponse("missing choices")
        msg = data["choices"][0].get("message") or {}
        content = msg.get("content")
        if content is None:
            raise PartialResponse("missing content")
        usage = data.get("usage")
        if not usage or usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
            raise UsageMissing("response missing usage tokens")
        return str(content), http_status, int(usage["prompt_tokens"]), int(usage["completion_tokens"])


# ---------------------------------------------------------------------------
# Isolated workflow executor (generated code sandbox)
# ---------------------------------------------------------------------------

def run_workflow_code_isolated(graph_code: str, *, problem: str = "1+1",
                               timeout: int = 20, memory_mb: int = 256,
                               pids_limit: int = 64) -> Dict[str, Any]:
    """Run generated Workflow in Docker with network/credential isolation.

    The container receives only a localhost gateway URL (if any) via a controlled
    interface — never host env secrets, never arbitrary egress.
    """
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        (td_path / "graph.py").write_text(graph_code, encoding="utf-8")
        (td_path / "runner.py").write_text(
            "import asyncio, json, sys\n"
            "sys.path.insert(0, '/work')\n"
            "from graph import Workflow\n"
            "async def main():\n"
            "    w = Workflow()\n"
            "    out = await w('1+1')\n"
            "    print(json.dumps({'ok': True, 'out': repr(out)[:200]}))\n"
            "asyncio.run(main())\n",
            encoding="utf-8",
        )
        cmd = [
            "docker", "run", "--rm",
            "--network", "none",
            "--memory", f"{memory_mb}m",
            "--memory-swap", f"{memory_mb}m",
            "--pids-limit", str(pids_limit),
            "-v", f"{td_path}:/work",
            "-w", "/work",
            "-e", "PYTHONUNBUFFERED=1",
            # deliberately NO host secrets, NO proxy, NO docker.sock
            "python:3.10-slim",
            "python", "runner.py",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "TIMEOUT", "returncode": 124}
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-500:],
            "stderr": proc.stderr[-500:],
        }


def install_aflow_gateway(gateway_llm: GatewayLLM) -> None:
    """Patch AFlow module factories so Optimizer and Workflow both use GatewayLLM."""
    import sys
    aflow = Path(__file__).resolve().parents[2] / "external" / "AFlow"
    if str(aflow) not in sys.path:
        sys.path.insert(0, str(aflow))
    import scripts.async_llm as async_llm_mod  # type: ignore
    import scripts.optimizer as optimizer_mod  # type: ignore
    import scripts.workflow as workflow_mod  # type: ignore

    factory = lambda cfg=None: gateway_llm  # noqa: E731
    async_llm_mod.create_llm_instance = factory
    async_llm_mod.AsyncLLM = lambda *a, **k: gateway_llm
    if hasattr(optimizer_mod, "create_llm_instance"):
        optimizer_mod.create_llm_instance = factory
    if hasattr(workflow_mod, "create_llm_instance"):
        workflow_mod.create_llm_instance = factory
