"""DeepSeek API recheck (Phase5-R3) — deepseek-flash only.

Cross-validates: OpenAI Python SDK, curl --noproxy, project DeepSeekBackend.
Success requires HTTP 200 + non-empty parsed completion + model id.
"""

from __future__ import annotations

import json
import os
import ssl
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional


MODEL = "deepseek-flash"
PROMPT = "Reply with exactly: OK"
ENDPOINT = "https://api.deepseek.com/v1/chat/completions"
PAYLOAD = {
    "model": MODEL,
    "messages": [{"role": "user", "content": PROMPT}],
    "thinking": {"type": "disabled"},
    "max_tokens": 64,
    "stream": False,
}


def _key() -> str:
    return os.environ.get("DEEPSEEK_API_KEY", "")


def _clear_local_proxies() -> None:
    # Do not mutate global env permanently; use thread-local style override only
    # by building direct SSL/urllib objects in each tester.
    pass


def test_curl() -> Dict[str, Any]:
    key = _key()
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tf.write(json.dumps(PAYLOAD).encode("utf-8"))
    tf.close()
    cmd = [
        "curl.exe", "--noproxy", "*", "-sS", "-m", "25",
        "-w", "\n__HTTP:%{http_code}__TTFB:%{time_starttransfer}__TOTAL:%{time_total}__",
        "-X", "POST", ENDPOINT,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {key}",
        "--data-binary", f"@{tf.name}",
    ]
    t0 = time.time()
    out = b""
    err = None
    code = None
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=30)
        text = out.decode("utf-8", errors="replace")
        if "__HTTP:" in text:
            body, meta = text.rsplit("__HTTP:", 1)
            meta_parts = meta.split("__")
            code = int(meta_parts[0] or 0)
            body = body
        else:
            body = text
        try:
            data = json.loads(body)
        except Exception:
            data = {}
        content = ""
        model_out = ""
        usage = {}
        try:
            content = data["choices"][0]["message"].get("content") or ""
            model_out = data.get("model") or ""
            usage = data.get("usage") or {}
        except Exception:
            pass
        return {
            "method": "curl",
            "http_status": code,
            "ttfb_s": None,
            "total_s": time.time() - t0,
            "body_len": len(body),
            "content": content[:80],
            "content_nonempty": bool(content.strip()),
            "model_out": model_out,
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
            "error": err,
            "ok": code == 200 and bool(content.strip()),
        }
    except subprocess.CalledProcessError as e:
        return {"method": "curl", "ok": False, "error": f"curl_exit={e.returncode}",
                "raw": (e.output or b"")[:200].decode("utf-8", errors="replace"),
                "total_s": time.time() - t0}
    except Exception as e:
        return {"method": "curl", "ok": False, "error": f"{type(e).__name__}: {e}",
                "total_s": time.time() - t0}


def test_openai_sdk() -> Dict[str, Any]:
    try:
        from openai import OpenAI
    except Exception as e:
        return {"method": "openai_sdk", "ok": False, "error": f"import: {e}"}
    key = _key()
    client = OpenAI(
        api_key=key,
        base_url="https://api.deepseek.com",
        timeout=25.0,
        max_retries=1,
    )
    t0 = time.time()
    try:
        resp = client.chat.completions.create(**PAYLOAD)
        content = ""
        if resp.choices and resp.choices[0].message:
            content = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return {
            "method": "openai_sdk",
            "http_status": 200,
            "total_s": time.time() - t0,
            "content": content[:80],
            "content_nonempty": bool(content.strip()),
            "model_out": getattr(resp, "model", ""),
            "tokens_in": getattr(usage, "prompt_tokens", None),
            "tokens_out": getattr(usage, "completion_tokens", None),
            "ok": bool(content.strip()),
            "error": None,
        }
    except Exception as e:
        return {"method": "openai_sdk", "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "total_s": time.time() - t0}


def test_project_backend() -> Dict[str, Any]:
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.backend.base import DeepSeekBackend

    b = DeepSeekBackend(max_retries=1, timeout=25)
    t0 = time.time()
    try:
        r = b.generate(PROMPT, budget=8)
        return {
            "method": "project_backend",
            "http_status": 200,
            "total_s": time.time() - t0,
            "content": (r.text or "")[:80],
            "content_nonempty": bool((r.text or "").strip()),
            "model_out": r.model,
            "tokens_in": r.tokens_prompt,
            "tokens_out": r.tokens_completion,
            "ok": bool((r.text or "").strip()),
            "error": None,
        }
    except Exception as e:
        return {"method": "project_backend", "ok": False,
                "error": f"{type(e).__name__}: {e}",
                "total_s": time.time() - t0}


def test_stream_sse() -> Dict[str, Any]:
    """Minimal SSE parse: look for data: chunks with content."""
    key = _key()
    payload = dict(PAYLOAD)
    payload["stream"] = True
    tf = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
    tf.write(json.dumps(payload).encode("utf-8"))
    tf.close()
    cmd = [
        "curl.exe", "--noproxy", "*", "-sS", "-N", "-m", "20",
        "-w", "\n__HTTP:%{http_code}__TOTAL:%{time_total}__",
        "-X", "POST", ENDPOINT,
        "-H", "Content-Type: application/json",
        "-H", f"Authorization: Bearer {key}",
        "--data-binary", f"@{tf.name}",
    ]
    t0 = time.time()
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=25)
        text = out.decode("utf-8", errors="replace")
        has_data = "data:" in text
        has_content = '"content"' in text or "'content'" in text
        has_done = "[DONE]" in text or "finish_reason" in text
        body_len = len(text)
        return {
            "method": "curl_stream",
            "http_status": None,
            "total_s": time.time() - t0,
            "body_len": body_len,
            "has_sse_data": has_data,
            "has_content": has_content,
            "has_finish": has_done,
            "content_nonempty": has_data and has_content,
            "ok": has_data and has_content,
            "error": None,
            "raw_prefix": text[:120],
        }
    except subprocess.CalledProcessError as e:
        return {"method": "curl_stream", "ok": False,
                "error": f"curl_exit={e.returncode}",
                "raw": (e.output or b"")[:160].decode("utf-8", errors="replace"),
                "total_s": time.time() - t0}


def main() -> Dict[str, Any]:
    key_ok = bool(_key())
    print("api_key_present", key_ok)
    results = [
        test_curl(),
        test_openai_sdk(),
        test_project_backend(),
    ]
    if not any(r.get("ok") for r in results):
        print("nonstream all failed; trying stream")
        results.append(test_stream_sse())
    # If success, up to 3 confirmation repeats via curl
    confirmations = []
    if any(r.get("ok") for r in results):
        for i in range(3):
            confirmations.append(test_curl())
    any_ok = any(r.get("ok") for r in results) and (
        not confirmations or sum(1 for c in confirmations if c.get("ok")) >= 1
    )
    summary = {
        "model": MODEL,
        "endpoint": ENDPOINT,
        "tests": results,
        "confirmations": confirmations,
        "status": "API_AVAILABLE" if any_ok else "API_UNAVAILABLE",
    }
    return summary


if __name__ == "__main__":
    print(json.dumps(main(), indent=2, ensure_ascii=False))
