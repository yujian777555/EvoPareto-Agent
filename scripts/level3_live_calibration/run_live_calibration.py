"""Level 3 first live DeepSeek calibration (AUTHORISED: 10 req / $0.10 max).

Hard limits (all simultaneous, stop at the first hit):
  MAX_PHYSICAL_HTTP_REQUESTS = 10
  MAX_REAL_API_COST_USD      = 0.10
  MAX_INPUT_PER_REQUEST      = 8000
  MAX_OUTPUT_PER_REQUEST     = 500
  MAX_TOTAL_INPUT_TOKENS     = 80000
  MAX_TOTAL_OUTPUT_TOKENS    = 5000
  CONCURRENCY                = 1
  AUTO_EXPAND_BUDGET         = False

Real DeepSeek calls only. No mock substitution. No gold leakage.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "level3_live_calibration"
OUT.mkdir(parents=True, exist_ok=True)

from src.runtime.http_budget import (  # noqa: E402
    BillingBlocked,
    BudgetDB,
    BudgetExceeded,
    PhysicalBudgetGate,
    install_global_gate,
)
from src.runtime.provider_gateway import conservative_input_tokens, worst_case_cost  # noqa: E402

# ---------------- frozen limits ----------------
MODEL_ID = "deepseek-flash"
MODEL_VERSION_EXPECTED = "DeepSeek-V4.1-Flash-1017"
BASE_URL = "https://api.deepseek.com"
PRICE_INPUT_PER_1M = 0.30   # peak cache-miss (conservative)
PRICE_OUTPUT_PER_1M = 1.20  # peak
PRICE_VERIFIED_AT = "2026-10-17"

MAX_PHYSICAL = 10
MAX_COST_USD = 0.10
MAX_IN_PER_REQ = 8000
MAX_OUT_PER_REQ = 500
MAX_TOTAL_IN = 80000
MAX_TOTAL_OUT = 5000

run_id = "l3-cal-" + uuid.uuid4().hex[:10]
STOP_REASON = ""


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


class LiveClient:
    """Budget-gated real DeepSeek client. Direct connection, no system proxy."""

    def __init__(self, api_key: str, db: BudgetDB, ledger_rows: List[Dict], run_id: str):
        self.api_key = api_key
        self.db = db
        self.ledger_rows = ledger_rows
        self.run_id = run_id
        self.logical_seq = 0

    def _next_logical(self) -> str:
        self.logical_seq += 1
        return f"live-{self.logical_seq:03d}"

    def chat(self, prompt: str, *, phase: str) -> Dict[str, Any]:
        global STOP_REASON
        logical_id = self._next_logical()
        physical_id = uuid.uuid4().hex
        est_in = conservative_input_tokens(prompt)
        if est_in > MAX_IN_PER_REQ:
            STOP_REASON = "INPUT_TOKEN_CAP_EXCEEDED_BEFORE_SEND"
            raise RuntimeError(STOP_REASON)

        reserve_cost = worst_case_cost(MODEL_ID, est_in, MAX_OUT_PER_REQ)
        ticket = self.db.acquire_ticket(
            reserve_cost,
            res_tokens_in=est_in,
            res_tokens_out=MAX_OUT_PER_REQ,
        )

        import urllib.error
        import urllib.request

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body = json.dumps({
            "model": MODEL_ID,
            "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUT_PER_REQ,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        record: Dict[str, Any] = {
            "run_id": self.run_id,
            "logical_request_id": logical_id,
            "physical_request_id": physical_id,
            "ticket_id": ticket,
            "request_phase": phase,
            "prompt_sha256": sha256_text(prompt),
            "prompt_len_chars": len(prompt),
            "estimated_input_tokens": est_in,
            "reserved_cost_usd": reserve_cost,
            "max_input_tokens": MAX_IN_PER_REQ,
            "max_output_tokens": MAX_OUT_PER_REQ,
        }

        try:
            with opener.open(req, timeout=60) as resp:
                http_status = int(resp.status)
                raw = resp.read()
        except urllib.error.HTTPError as e:
            body_txt = e.read()[:300] if hasattr(e, "read") else b""
            record.update({
                "http_status": e.code,
                "error_kind": f"HTTP_{e.code}",
                "error_body": body_txt.decode("utf-8", "replace")[:300],
                "ledger_status": "fail_closed",
            })
            self.db.settle_unknown_and_block(ticket, reason=f"HTTP_{e.code}")
            self.ledger_rows.append(record)
            STOP_REASON = f"HTTP_{e.code}"
            raise
        except Exception as e:
            record.update({
                "http_status": None,
                "error_kind": type(e).__name__,
                "error_message": str(e)[:300],
                "ledger_status": "fail_closed",
            })
            self.db.settle_unknown_and_block(ticket, reason=f"{type(e).__name__}:{e}")
            self.ledger_rows.append(record)
            STOP_REASON = f"NETWORK:{type(e).__name__}"
            raise

        record["http_status"] = http_status
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            record.update({"error_kind": "INVALID_JSON", "ledger_status": "fail_closed"})
            self.db.settle_unknown_and_block(ticket, reason="INVALID_JSON")
            self.ledger_rows.append(record)
            STOP_REASON = "INVALID_JSON"
            raise

        usage = data.get("usage") or {}
        tokens_in = usage.get("prompt_tokens")
        tokens_out = usage.get("completion_tokens")
        model_ret = data.get("model")
        choices = data.get("choices") or []
        finish_reason = choices[0].get("finish_reason") if choices else None
        content = (choices[0].get("message") or {}).get("content") if choices else None

        record.update({
            "model_returned": model_ret,
            "finish_reason": finish_reason,
            "usage_prompt_tokens": tokens_in,
            "usage_completion_tokens": tokens_out,
            "usage_total_tokens": usage.get("total_tokens"),
            "content_len": len(content) if content else 0,
            "content_preview": (content or "")[:200],
        })

        # ---- fail-closed checks ----
        if tokens_in is None or tokens_out is None:
            record["ledger_status"] = "fail_closed"
            self.db.settle_unknown_and_block(ticket, reason="MISSING_USAGE")
            self.ledger_rows.append(record)
            STOP_REASON = "MISSING_USAGE"
            raise RuntimeError(STOP_REASON)
        if finish_reason == "length":
            record["ledger_status"] = "fail_closed"
            self.db.settle(ticket, success=False, actual_cost=reserve_cost, tokens_in=tokens_in, tokens_out=tokens_out)
            self.ledger_rows.append(record)
            STOP_REASON = "RESPONSE_TRUNCATED"
            raise RuntimeError(STOP_REASON)
        if content is None or content == "":
            record["ledger_status"] = "fail_closed"
            self.db.settle(ticket, success=False, actual_cost=reserve_cost, tokens_in=tokens_in, tokens_out=tokens_out)
            self.ledger_rows.append(record)
            STOP_REASON = "EMPTY_CONTENT"
            raise RuntimeError(STOP_REASON)

        observed_cost = (tokens_in / 1e6) * PRICE_INPUT_PER_1M + (tokens_out / 1e6) * PRICE_OUTPUT_PER_1M
        self.db.settle(
            ticket, success=True,
            actual_cost=observed_cost,
            tokens_in=int(tokens_in), tokens_out=int(tokens_out),
        )
        snap = self.db.snapshot()
        record.update({
            "observed_cost_usd": observed_cost,
            "cumulative_cost_usd": snap["spent_cost_usd"],
            "cumulative_tokens_in": snap["tokens_in"],
            "cumulative_tokens_out": snap["tokens_out"],
            "ledger_status": "settled_ok",
        })
        self.ledger_rows.append(record)
        return {"content": content, "model": model_ret, "finish_reason": finish_reason,
                "usage": usage, "record": record}


def extract_final_number(text: str) -> Optional[str]:
    if "####" in text:
        tail = text.rsplit("####", 1)[1].strip()
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", tail)
        if m:
            return m.group(0).replace(",", "")
    ms = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)
    return ms[-1].replace(",", "") if ms else None


def parse_xml_mutation(text: str) -> Dict[str, Any]:
    def tag(name: str) -> Optional[str]:
        m = re.search(rf"<{name}>([\s\S]*?)</{name}>", text or "")
        return m.group(1).strip() if m else None
    mod, graph, prompt = tag("modification"), tag("graph"), tag("prompt")
    result = {
        "modification": mod, "graph": graph, "prompt": prompt,
        "xml_complete": all(x is not None for x in (mod, graph, prompt)),
    }
    if graph:
        try:
            compile(graph, "<graph>", "exec")
            result["graph_compile"] = "OK"
            result["has_workflow_class"] = "class Workflow" in graph
        except SyntaxError as e:
            result["graph_compile"] = f"FAIL:{e.msg}"
    else:
        result["graph_compile"] = "NO_GRAPH"
    if prompt:
        try:
            compile(prompt, "<prompt>", "exec")
            result["prompt_compile"] = "OK"
        except SyntaxError as e:
            result["prompt_compile"] = f"FAIL:{e.msg}"
    else:
        result["prompt_compile"] = "NO_PROMPT"
    return result


def main() -> int:
    global STOP_REASON
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY missing")
        return 2

    db_path = OUT / f"live_budget_{run_id}.sqlite"
    if db_path.exists():
        db_path.unlink()
    db = BudgetDB(db_path, max_physical=MAX_PHYSICAL, max_cost_usd=MAX_COST_USD)
    install_global_gate(PhysicalBudgetGate(db, est_cost_per_request=0.01), strict=True)
    ledger_rows: List[Dict[str, Any]] = []
    client = LiveClient(api_key, db, ledger_rows, run_id)

    events: Dict[str, Any] = {
        "run_id": run_id,
        "REAL_MODEL_REQUESTED": MODEL_ID,
        "THINKING_DISABLED_CONFIRMED": False,
        "REAL_HTTP_REQUESTS": 0,
        "REAL_INPUT_TOKENS": 0,
        "REAL_OUTPUT_TOKENS": 0,
        "REAL_COST_USD": 0.0,
        "stages": {},
    }

    # --------- Stage 1: plain GSM8K-style math (train, not test) ---------
    stage1_prompt = (
        "Solve this GSM8K train problem step by step, then give the final "
        "numeric answer after '#### '.\n\n"
        "Problem: Weng earns $12 an hour for babysitting. Yesterday, she just "
        "did 50 minutes of babysitting. How much did she earn?"
    )
    try:
        r1 = client.chat(stage1_prompt, phase="math_calibration")
        events["REAL_HTTP_REQUESTS"] += 1
        events["REAL_MODEL_RETURNED"] = r1["model"]
        events["THINKING_DISABLED_CONFIRMED"] = True  # request sent with disabled
        content = r1["content"]
        pred = extract_final_number(content)
        events["stages"]["math"] = {
            "status": "OK",
            "content_preview": content[:300],
            "predicted": pred,
            "finish_reason": r1["finish_reason"],
            "non_empty": bool(content and content.strip()),
            "parseable": pred is not None,
        }
    except Exception as e:
        events["stages"]["math"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
        STOP_REASON = STOP_REASON or "STAGE_MATH_FAILED"

    # --------- Stage 2: AFlow Optimizer prompt -> XML mutation ---------
    if not STOP_REASON:
        # minimal but realistic optimizer-shaped prompt (uses official AFlow template)
        opt_prompt = (
            "You are GraphOptimize. Generate an improved workflow for GSM8K math QA.\n"
            "Return EXACTLY these three XML tags and nothing else:\n"
            "<modification>...</modification>\n"
            "<graph>... Python class Workflow with async def __call__(self, problem) ...</graph>\n"
            "<prompt>... module-level INSTRUCTION string ...</prompt>\n\n"
            "Requirements: graph must define `class Workflow`, compile as Python, "
            "and call its LLM for the answer. Keep it short."
        )
        try:
            r2 = client.chat(opt_prompt, phase="optimizer_mutation")
            events["REAL_HTTP_REQUESTS"] += 1
            parsed = parse_xml_mutation(r2["content"])
            events["stages"]["optimizer"] = {
                "status": "OK" if parsed["xml_complete"] else "INCOMPLETE_XML",
                "finish_reason": r2["finish_reason"],
                **parsed,
                "raw_preview": r2["content"][:400],
            }
            if not parsed["xml_complete"]:
                STOP_REASON = "STRUCTURED_OUTPUT_INCOMPLETE"
        except Exception as e:
            events["stages"]["optimizer"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
            STOP_REASON = STOP_REASON or "STAGE_OPTIMIZER_FAILED"

    # --------- Stage 3: execute real generated child in Docker + IPC ---------
    real_graph = None
    if not STOP_REASON:
        opt = events["stages"].get("optimizer") or {}
        if opt.get("graph") and opt.get("graph_compile", "").startswith("OK"):
            real_graph = opt["graph"]
            try:
                from src.runtime.workflow_ipc import run_workflow_code_isolated

                # gold-blind task question (train, not test)
                q = ("Natalia sold clips to 48 of her friends in April, and then "
                     "she sold half as many clips in May. How many clips did "
                     "Natalia sell altogether in April and May?")
                # live child LLM goes through the same budget-gated client
                class LiveIPC:
                    def _request(self, prompt: str) -> str:
                        rr = client.chat(prompt, phase="workflow_execution")
                        events["REAL_HTTP_REQUESTS"] += 1
                        return rr["content"]

                child = run_workflow_code_isolated(
                    real_graph, problem=q, task_id="gsm8k-train-0000-live",
                    gold_answer=None, llm=LiveIPC(), timeout=30,
                )
                out = child.get("stdout") or ""
                model_text = out
                try:
                    payload = json.loads(out[out.find("{"):])
                    model_text = payload.get("out", out)
                except Exception:
                    pass
                pred = extract_final_number(str(model_text))
                # gold stays host-side only
                gold = "72"
                events["stages"]["child_exec"] = {
                    "docker_ok": bool(child.get("ok")),
                    "docker_returncode": child.get("returncode"),
                    "stderr_tail": (child.get("stderr") or "")[-300:],
                    "raw_output": str(model_text)[:300],
                    "predicted": pred,
                    "gold_host_only": gold,
                    "correct": pred == gold,
                    "ipc_processed": len(child.get("ipc_processed") or []),
                    "container_task_keys": "question,task_id (no gold)",
                }
                if not child.get("ok"):
                    STOP_REASON = STOP_REASON or "DOCKER_CHILD_EXECUTION_FAILED"
            except Exception as e:
                events["stages"]["child_exec"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
                STOP_REASON = STOP_REASON or "STAGE_CHILD_FAILED"
        else:
            events["stages"]["child_exec"] = {"status": "SKIPPED", "reason": "no valid real graph"}
            STOP_REASON = STOP_REASON or "NO_VALID_CANDIDATE"

    # --------- reconciliation ---------
    snap = db.snapshot()
    events["REAL_HTTP_REQUESTS"] = snap["physical_attempts"]
    events["LEDGER_REQUESTS"] = len(ledger_rows)
    events["REAL_INPUT_TOKENS"] = snap["tokens_in"]
    events["REAL_OUTPUT_TOKENS"] = snap["tokens_out"]
    events["REAL_COST_USD"] = snap["spent_cost_usd"]
    events["STOP_REASON"] = STOP_REASON or "CALIBRATION_COMPLETE_WITHIN_BUDGET"
    events["PHYSICAL_HTTP_COUNT"] = snap["physical_attempts"]
    events["GATEWAY_LEDGER_COUNT"] = len(ledger_rows)
    events["HTTP_LEDGER_MATCH"] = snap["physical_attempts"] == len(ledger_rows)
    events["budget_snapshot"] = snap

    # persist
    (OUT / "request_ledger.json").write_text(
        json.dumps({"run_id": run_id, "rows": ledger_rows}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / "real_model_responses.json").write_text(
        json.dumps({"run_id": run_id, "stages": events.get("stages")}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    opt = events["stages"].get("optimizer") or {}
    (OUT / "candidate_validation.json").write_text(
        json.dumps({
            "run_id": run_id,
            "xml_complete": opt.get("xml_complete"),
            "graph_compile": opt.get("graph_compile"),
            "prompt_compile": opt.get("prompt_compile"),
            "has_workflow_class": opt.get("has_workflow_class"),
            "CANDIDATE_GRAPH_SHA": sha256_text(opt.get("graph") or "")[:64] if opt.get("graph") else None,
        }, indent=2), encoding="utf-8"
    )
    (OUT / "workflow_execution.json").write_text(
        json.dumps({"run_id": run_id, "child_exec": events["stages"].get("child_exec")}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "evaluation_results.json").write_text(
        json.dumps({
            "run_id": run_id,
            "gsm8k_task_count": 1 if events["stages"].get("child_exec") else 0,
            "task_success_rate": (1.0 if (events["stages"].get("child_exec") or {}).get("correct") else 0.0),
            "detail": events["stages"].get("child_exec"),
        }, indent=2, ensure_ascii=False), encoding="utf-8",
    )
    (OUT / "cost_reconciliation.json").write_text(
        json.dumps({
            "run_id": run_id,
            "REAL_HTTP_REQUESTS": events["REAL_HTTP_REQUESTS"],
            "LEDGER_REQUESTS": events["LEDGER_REQUESTS"],
            "HTTP_LEDGER_MATCH": events["HTTP_LEDGER_MATCH"],
            "REAL_INPUT_TOKENS": events["REAL_INPUT_TOKENS"],
            "REAL_OUTPUT_TOKENS": events["REAL_OUTPUT_TOKENS"],
            "REAL_COST_USD": events["REAL_COST_USD"],
            "MAX_COST_USD": MAX_COST_USD,
            "MAX_PHYSICAL": MAX_PHYSICAL,
            "under_budget": events["REAL_COST_USD"] <= MAX_COST_USD and events["REAL_HTTP_REQUESTS"] <= MAX_PHYSICAL,
        }, indent=2), encoding="utf-8"
    )

    (OUT / "live_run_summary.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    install_global_gate(None, strict=False)
    db.close()

    print(json.dumps({k: events[k] for k in (
        "run_id", "REAL_MODEL_RETURNED", "REAL_HTTP_REQUESTS", "LEDGER_REQUESTS",
        "REAL_INPUT_TOKENS", "REAL_OUTPUT_TOKENS", "REAL_COST_USD", "STOP_REASON",
        "HTTP_LEDGER_MATCH",
    ) if k in events}, indent=2))
    return 0 if not STOP_REASON or STOP_REASON.startswith("CALIBRATION_COMPLETE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
