"""HTTP JSON POST helper with single-transport physical accounting.

Exactly one physical send per post_json call (no curl/urllib double-fire).
BillingBlocked / BudgetExceeded / GateRequired never retry.
Unknown cost settles + blocks in one atomic ledger transaction.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, Optional, Tuple


def _proxy_url() -> Optional[str]:
    """Return proxy URL only if explicitly enabled (EVO_USE_PROXY=1)."""
    if os.environ.get("EVO_USE_PROXY", "").strip() not in ("1", "true", "yes"):
        return None
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return None


def _pick_transport() -> str:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    return "curl" if curl else "urllib"


def post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Dict[str, str],
    *,
    timeout: float = 60.0,
    max_retries: int = 2,
    retry_backoff: float = 1.5,
    before_send: Optional[Callable[[], None]] = None,
) -> Tuple[int, Dict[str, Any]]:
    """POST JSON with one physical attempt per try and billing fail-fast.

    Order per try:
      pre_send_ticket (BEGIN IMMEDIATE, checks billing_blocked)
        -> single transport send
        -> settle once (known cost) OR settle_unknown_and_block (atomic)
    """
    body = json.dumps(payload).encode("utf-8")
    last_err: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        from src.runtime.http_budget import (
            BillingBlocked,
            BudgetExceeded,
            GateRequired,
            get_global_gate,
            pre_send_ticket,
            settle_ticket,
        )

        # Ticket BEFORE network. BillingBlocked must abort, never retry.
        ticket = pre_send_ticket()
        settled = False
        try:
            if before_send is not None:
                before_send()
            mode = _pick_transport()
            if mode == "curl":
                status, data = _post_curl(url, body, headers, timeout)
            else:
                status, data = _post_urllib(url, body, headers, timeout)

            from src.backend.cost_status import estimate_cost

            usage = data.get("usage") or {} if isinstance(data, dict) else {}
            tokens_in = usage.get("prompt_tokens")
            tokens_out = usage.get("completion_tokens")
            model = str(data.get("model") or "deepseek-flash")
            cstat = estimate_cost(model, tokens_in, tokens_out)

            http_ok = 200 <= int(status) < 300
            completion_ok = False
            if http_ok and isinstance(data, dict):
                try:
                    text = data["choices"][0]["message"].get("content") or ""
                    completion_ok = bool(str(text).strip())
                except Exception:
                    completion_ok = False

            tin = int(tokens_in or 0)
            tout = int(tokens_out or 0)
            if cstat.is_known:
                settle_ticket(
                    ticket,
                    success=completion_ok,
                    tokens_in=tin,
                    tokens_out=tout,
                    actual_cost=cstat.cost,
                )
                settled = True
            else:
                # Unknown cost: settle + persistent billing block in ONE
                # transaction, then abort this call. Never present unknown
                # cost as a successful zero-cost result.
                gate = get_global_gate()
                if gate is None:
                    raise RuntimeError(
                        f"unknown cost ({cstat.status}) without budget gate — "
                        "refusing to continue"
                    )
                gate.db.settle_unknown_and_block(
                    ticket,
                    reason=f"{cstat.status}:{cstat.detail}",
                    tokens_in=tin,
                    tokens_out=tout,
                )
                settled = True
                if isinstance(data, dict):
                    data["_cost_status"] = cstat.to_dict()
                raise BillingBlocked(
                    f"unknown cost aborted after atomic block: "
                    f"{cstat.status}:{cstat.detail}"
                )
            if isinstance(data, dict):
                data["_cost_status"] = cstat.to_dict()
            return status, data
        except (BudgetExceeded, GateRequired, BillingBlocked):
            # Pre-send denial or ledger refusal: no retry.
            raise
        except Exception as e:
            if not settled and ticket:
                # Transport failure after ticket: count the physical attempt.
                # Response body unavailable => not a priced unknown-cost event.
                try:
                    settle_ticket(ticket, success=False)
                    settled = True
                except Exception:
                    pass
            last_err = e
            msg = str(e)
            if any(x in msg for x in ("402", "Payment Required", "401", "403")):
                raise
            if attempt < max_retries:
                import time

                time.sleep(retry_backoff * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP POST failed: {last_err}") from last_err
    raise RuntimeError(f"HTTP POST failed: {last_err}")


def _post_urllib(
    url: str, body: bytes, headers: Dict[str, str], timeout: float
) -> Tuple[int, Dict[str, Any]]:
    proxy = _proxy_url()
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
    else:
        opener = urllib.request.build_opener()
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return int(resp.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        # Normalize: HTTP status + parsed body, same shape as curl path.
        raw = e.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            data = {"raw": raw[:500]}
        return int(e.code), data


def _post_curl(
    url: str, body: bytes, headers: Dict[str, str], timeout: float
) -> Tuple[int, Dict[str, Any]]:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise RuntimeError("curl not found")
    import tempfile

    proxy = _proxy_url()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tf:
        tf.write(body)
        body_path = tf.name
    if proxy:
        cmd = [curl, "-x", proxy, "-sS", "-m", str(int(timeout)), "-w", "\n%{http_code}", "-X", "POST", url]
    else:
        cmd = [curl, "--noproxy", "*", "-sS", "-m", str(int(timeout)), "-w", "\n%{http_code}", "-X", "POST", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["--data-binary", f"@{body_path}"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout + 5)
        text = out.decode("utf-8", errors="replace")
        # -w appends "\n{http_code}" as the final line.
        lines = text.rsplit("\n", 1)
        if len(lines) == 2:
            body_text, code_str = lines
            code = int(code_str.strip() or "0")
        else:
            body_text, code = text, 0
        data = json.loads(body_text) if body_text.strip() else {}
        return code, data
    finally:
        try:
            os.unlink(body_path)
        except OSError:
            pass
