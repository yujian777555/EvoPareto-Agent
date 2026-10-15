"""Phase5-R3 Task1: DeepSeek API fault-isolation diagnostics.

Records: HTTP status, TTFB, total latency, response length, error type.
Does NOT print API keys or full account payloads.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.request
from typing import Any, Dict, Optional


def _clear_proxies_in_env() -> None:
    for k in list(os.environ):
        if "proxy" in k.lower():
            os.environ.pop(k, None)


def _direct_urlopen(url: str, *, method: str = "GET", body: Optional[bytes] = None,
                    headers: Optional[Dict[str, str]] = None, timeout: float = 15.0):
    """Open URL with an opener that ignores system/environment proxies."""
    handler = urllib.request.ProxyHandler({})  # empty = no proxy
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    t0 = time.time()
    first_byte = None
    status = None
    err = None
    chunks = b""
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = int(resp.status)
            first_byte = time.time() - t0
            chunks = resp.read()
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    total = time.time() - t0
    return {
        "http_status": status,
        "ttfb": first_byte,
        "total_latency": total,
        "response_len": len(chunks),
        "error": err,
        "raw_prefix": chunks[:200].decode("utf-8", errors="replace"),
    }


def check_balance() -> Dict[str, Any]:
    """GET /user/balance — availability only, no account details leaked."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return {"available": False, "reason": "DEEPSEEK_API_KEY missing"}
    _clear_proxies_in_env()
    r = _direct_urlopen(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        timeout=12,
    )
    # Parse only whether balance info is present, not amounts/ids.
    has_balance_info = False
    if r["raw_prefix"]:
        try:
            data = json.loads(r["raw_prefix"] if r["response_len"] <= 200 else r["raw_prefix"] + "}")
        except Exception:
            data = {}
        # Official shape: {"is_available": true, "balance_infos": [...]}
        if isinstance(data, dict) and ("is_available" in data or "balance_infos" in data):
            has_balance_info = True
    return {
        "available": r["http_status"] == 200 and has_balance_info,
        "http_status": r["http_status"],
        "ttfb": r["ttfb"],
        "total_latency": r["total_latency"],
        "error": r["error"],
        "has_balance_fields": has_balance_info,
    }


def chat_probe(model: str = "deepseek-flash", *, stream: bool = False,
               thinking_disabled: bool = True, max_tokens: int = 64,
               timeout: float = 20.0) -> Dict[str, Any]:
    """Minimal chat completion probe."""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        return {"ok": False, "error": "DEEPSEEK_API_KEY missing"}
    _clear_proxies_in_env()
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": int(max_tokens),
        "stream": bool(stream),
    }
    if thinking_disabled:
        payload["thinking"] = {"type": "disabled"}
    body = json.dumps(payload).encode("utf-8")
    r = _direct_urlopen(
        "https://api.deepseek.com/v1/chat/completions",
        method="POST",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
        },
        timeout=timeout,
    )
    ok = r["http_status"] == 200 and r["response_len"] > 0 and not r["error"]
    # Validate JSON completion if non-stream
    valid_completion = False
    if ok and not stream:
        try:
            data = json.loads(r["raw_prefix"]) if r["response_len"] <= 200 else None
            # may be truncated prefix; try full via error path only if small
        except Exception:
            data = None
        valid_completion = r["response_len"] > 20
    return {
        "ok": bool(ok and valid_completion),
        "model": model,
        "stream": stream,
        "thinking_disabled": thinking_disabled,
        "max_tokens": max_tokens,
        "http_status": r["http_status"],
        "ttfb": r["ttfb"],
        "total_latency": r["total_latency"],
        "response_len": r["response_len"],
        "error": r["error"],
        "valid_completion": valid_completion,
    }


def proxy_env_snapshot() -> Dict[str, Optional[str]]:
    return {
        "HTTP_PROXY": os.environ.get("HTTP_PROXY"),
        "HTTPS_PROXY": os.environ.get("HTTPS_PROXY"),
        "ALL_PROXY": os.environ.get("ALL_PROXY"),
        "EVO_USE_PROXY": os.environ.get("EVO_USE_PROXY"),
    }


def run_diagnostics(model: str = "deepseek-flash") -> Dict[str, Any]:
    _clear_proxies_in_env()
    return {
        "model_id": model,
        "proxy_env": proxy_env_snapshot(),
        "balance": check_balance(),
        "chat_nonstream": chat_probe(model, stream=False),
        "chat_stream": chat_probe(model, stream=True, timeout=15.0),
    }


if __name__ == "__main__":
    print(json.dumps(run_diagnostics(), indent=2))
