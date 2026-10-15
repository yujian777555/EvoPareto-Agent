"""HTTP JSON POST helper that works behind HTTP CONNECT proxies.

urllib/requests may stall on some local proxies; curl.exe's CONNECT tunnel
is reliable. We try urllib first, then fall back to curl.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple


def _proxy_url() -> Optional[str]:
    """Return proxy URL only if explicitly enabled (EVO_USE_PROXY=1).

    Phase5-R3: default is **direct** connection (bypass local/global proxies).
    """
    if os.environ.get("EVO_USE_PROXY", "").strip() not in ("1", "true", "yes"):
        return None
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        v = os.environ.get(k, "").strip()
        if v:
            return v
    return None


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
    """POST JSON with physical-attempt accounting and billing fail-fast."""
    body = json.dumps(payload).encode("utf-8")
    last_err: Exception | None = None
    # curl is preferred (handles TLS + optional --noproxy reliably).
    attempts = ("curl", "urllib")

    def _send(mode: str) -> Tuple[int, Dict[str, Any]]:
        # Fail-closed pre-send ticket. Any error here aborts BEFORE network.
        from src.runtime.http_budget import (
            BudgetExceeded,
            GateRequired,
            pre_send_ticket,
            settle_ticket,
        )

        ticket = pre_send_ticket()
        try:
            if mode == "curl":
                status, data = _post_curl(url, body, headers, timeout)
            else:
                status, data = _post_urllib(url, body, headers, timeout)
            settle_ticket(ticket, success=True)
            return status, data
        except (BudgetExceeded, GateRequired):
            raise
        except Exception:
            # Physical attempt occurred (or transport failed after send).
            settle_ticket(ticket, success=False)
            raise

    last_err: Exception | None = None
    for attempt in range(max_retries + 1):
        for mode in attempts:
            try:
                return _send(mode)
            except (BudgetExceeded, GateRequired):
                raise
            except Exception as e:
                last_err = e
                msg = str(e)
                if "402" in msg or "Payment Required" in msg:
                    raise
                if "401" in msg or "403" in msg:
                    raise
        if attempt < max_retries:
            import time

            time.sleep(retry_backoff * (attempt + 1))
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
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return int(resp.status), json.loads(raw) if raw else {}


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
    cmd = [curl, "--noproxy", "*", "-sS", "-m", str(int(timeout)), "-w", "\n%{http_code}", "-X", "POST", url]
    if proxy:
        # Explicit opt-in proxy path.
        cmd = [curl, "-x", proxy, "-sS", "-m", str(int(timeout)), "-w", "\n%{http_code}", "-X", "POST", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    cmd += ["--data-binary", f"@{body_path}"]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=timeout + 5)
        text = out.decode("utf-8", errors="replace")
        # last line is http_code from -w
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
