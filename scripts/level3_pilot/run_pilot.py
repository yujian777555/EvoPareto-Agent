"""Level 3 real Pilot — minimal first slice. AUTHORIZED max $5 cumulative.

Shared authorization across all runs (never reset by run-id / DB path).
Concurrency 1. Hard caps on every request.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results" / "level3_pilot"
OUT.mkdir(parents=True, exist_ok=True)

from src.runtime.auth_ledger import (  # noqa: E402
    AuthBudgetLedger,
    AuthorizationMissing,
    AuthorizationRecord,
    BudgetExceeded,
    UnifiedBudgetGate,
    UnknownBillingBlocked,
    open_production_authorization,
)
from src.runtime.provider_gateway import conservative_input_tokens, worst_case_cost  # noqa: E402
from src.runtime.workflow_ipc import run_workflow_code_isolated  # noqa: E402
from src.benchmark.gsm8k_tasks import evaluate_workflow_output, load_offline_tasks  # noqa: E402

# ---- frozen pilot configuration ----
MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_INPUT_PER_REQUEST = 8000
# Phase-specific output caps (Pilot-R1): optimizer XML needs more room.
PHASE_OUTPUT_CAPS = {
    "pilot_math": 500,
    "pilot_optimizer": 1800,
    "pilot_workflow_ipc": 500,
}
MAX_OUTPUT_PER_REQUEST = 500  # default; per-phase override below
MAX_PHYSICAL = 300
MAX_COST_USD = 5.00
MAX_TOTAL_IN = 2_000_000
MAX_TOTAL_OUT = 200_000
PRICE_IN_PER_1M = 0.30   # peak cache-miss (conservative)
PRICE_OUT_PER_1M = 1.20

SECRET = hashlib.sha256(
    (os.environ.get("DEEPSEEK_API_KEY", "") + "|level3-pilot|v1").encode("utf-8")
).hexdigest()

run_id = "pilot-" + uuid.uuid4().hex[:10]
STOP_REASON = ""


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def extract_num(text: str):
    import re

    if "####" in str(text):
        tail = str(text).rsplit("####", 1)[1].strip()
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", tail)
        if m:
            return m.group(0).replace(",", "")
    ms = re.findall(r"-?\d[\d,]*(?:\.\d+)?", str(text))
    return ms[-1].replace(",", "") if ms else None


def parse_xml(text: str):
    import re

    def tag(name):
        m = re.search(rf"<{name}>([\s\S]*?)</{name}>", text or "")
        return m.group(1).strip() if m else None
    mod, graph, prompt = tag("modification"), tag("graph"), tag("prompt")
    out = {"modification": mod, "graph": graph, "prompt": prompt,
           "xml_complete": all(x is not None for x in (mod, graph, prompt))}
    if graph:
        try:
            compile(graph, "<graph>", "exec")
            out["graph_compile"] = "OK"
            out["has_workflow"] = "class Workflow" in graph
        except SyntaxError as e:
            out["graph_compile"] = f"FAIL:{e.msg}"
    return out


def main() -> int:
    global STOP_REASON
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY missing")
        return 2

    events: Dict[str, Any] = {
        "run_id": run_id,
        "REAL_MODEL_REQUESTED": MODEL_ID,
        "authorization_mode": "SHARED_CUMULATIVE",
        "max_cost_usd": MAX_COST_USD,
        "stages": {},
    }

    # ---- authorization: persistent OUTSIDE-Git record; NEVER auto-create ----
    # P0 fix: deleting/rolling back the git copy must NOT mint a new $5 quota.
    rec_path = Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json"
    try:
        record = AuthorizationRecord.open_existing(rec_path, secret_key=SECRET)
        events["authorization_mode"] = "REUSED_PERSISTENT"
        events["authorization_path"] = str(rec_path)
    except AuthorizationMissing as e:
        events["failure"] = f"AUTHORIZATION_MISSING_FAIL_CLOSED:{e}"
        events["STOP_REASON"] = "AUTHORIZATION_RECORD_MISSING"
        (OUT / "pilot_latest_summary.json").write_text(
            json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps({"status": "FAIL_CLOSED_NO_AUTHORIZATION", "error": str(e)}, indent=2))
        return 3

    # ---- working DB is per-run but shares the record ----
    db = AuthBudgetLedger(OUT / f"pilot_budget_{run_id}.sqlite", record)
    # crash recovery: any stale RESERVED rows -> unknown billing block
    recovered = db.recover_stale_reservations()
    if recovered:
        events["crash_recovered_rows"] = recovered

    gate = UnifiedBudgetGate(db, default_max_in=MAX_INPUT_PER_REQUEST,
                             default_max_out=1800)

    ledger_rows: List[Dict[str, Any]] = []

    def chat(prompt: str, *, phase: str) -> Dict[str, Any]:
        global STOP_REASON
        est_in = conservative_input_tokens(prompt)
        if est_in > MAX_INPUT_PER_REQUEST:
            STOP_REASON = "INPUT_TOKEN_CAP_EXCEEDED"
            raise RuntimeError(STOP_REASON)
        out_cap = PHASE_OUTPUT_CAPS.get(phase, MAX_OUTPUT_PER_REQUEST)
        # reservation, request max_tokens and worst-case cost share the SAME cap
        reserve_cost = worst_case_cost(MODEL_ID, est_in, out_cap)
        physical_id = gate.begin_request(
            run_id=run_id, phase=phase, prompt_sha=sha256_text(prompt),
            res_in=est_in, res_out=out_cap, res_cost=reserve_cost,
        )
        import urllib.error
        import urllib.request

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body = json.dumps({
            "model": MODEL_ID,
            "thinking": {"type": "disabled"},
            "max_tokens": out_cap,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
        )
        rec: Dict[str, Any] = {
            "run_id": run_id, "physical_request_id": physical_id,
            "request_phase": phase, "prompt_sha256": sha256_text(prompt),
            "estimated_input_tokens": est_in, "reserved_cost_usd": reserve_cost, "max_output_tokens": out_cap,
        }
        try:
            with opener.open(req, timeout=90) as resp:
                http_status = int(resp.status)
                raw = resp.read()
        except urllib.error.HTTPError as e:
            rec.update({"http_status": e.code, "error_kind": f"HTTP_{e.code}",
                        "ledger_status": "fail_closed"})
            gate.complete_unknown(physical_id, reason=f"HTTP_{e.code}")
            ledger_rows.append(rec)
            STOP_REASON = f"HTTP_{e.code}"
            raise
        except Exception as e:
            rec.update({"error_kind": type(e).__name__, "ledger_status": "fail_closed"})
            gate.complete_unknown(physical_id, reason=f"{type(e).__name__}:{e}")
            ledger_rows.append(rec)
            STOP_REASON = f"NETWORK:{type(e).__name__}"
            raise

        data = json.loads(raw.decode("utf-8"))
        usage = data.get("usage") or {}
        t_in, t_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        model_ret = data.get("model")
        choices = data.get("choices") or []
        finish = choices[0].get("finish_reason") if choices else None
        content = (choices[0].get("message") or {}).get("content") if choices else None

        rec.update({"http_status": http_status, "model_returned": model_ret,
                    "finish_reason": finish,
                    "usage_prompt_tokens": t_in, "usage_completion_tokens": t_out,
                    "content_preview": (content or "")[:200]})

        if t_in is None or t_out is None:
            gate.complete_unknown(physical_id, reason="MISSING_USAGE")
            rec["ledger_status"] = "fail_closed"
            ledger_rows.append(rec)
            STOP_REASON = "MISSING_USAGE"
            raise RuntimeError(STOP_REASON)
        if finish == "length":
            gate.complete_actual(physical_id, actual_in=int(t_in), actual_out=int(t_out),
                                 observed_cost=reserve_cost, http_status=http_status,
                                 model_returned=model_ret, finish_reason=finish)
            rec["ledger_status"] = "truncated"
            ledger_rows.append(rec)
            STOP_REASON = "RESPONSE_TRUNCATED"
            raise RuntimeError(STOP_REASON)
        if not content:
            gate.complete_actual(physical_id, actual_in=int(t_in), actual_out=int(t_out),
                                 observed_cost=reserve_cost, http_status=http_status,
                                 model_returned=model_ret, finish_reason=finish)
            rec["ledger_status"] = "empty"
            ledger_rows.append(rec)
            STOP_REASON = "EMPTY_CONTENT"
            raise RuntimeError(STOP_REASON)

        cost = (t_in / 1e6) * PRICE_IN_PER_1M + (t_out / 1e6) * PRICE_OUT_PER_1M
        gate.complete_actual(physical_id, actual_in=int(t_in), actual_out=int(t_out),
                             observed_cost=cost, http_status=http_status,
                             model_returned=model_ret, finish_reason=finish)
        rec["observed_cost_usd"] = cost
        rec["ledger_status"] = "settled_ok"
        ledger_rows.append(rec)
        return {"content": content, "model": model_ret, "finish_reason": finish}

    # ================= minimal real experiment =================
    # Stage 1: one GSM8K train math task
    try:
        q1 = ("Weng earns $12 an hour for babysitting. Yesterday, she just did "
              "50 minutes of babysitting. How much did she earn?")
        r1 = chat(
            "Solve this GSM8K train problem step by step, then give the final "
            "numeric answer after '#### '.\n\nProblem: " + q1,
            phase="pilot_math",
        )
        pred = extract_num(r1["content"])
        events["stages"]["math"] = {
            "status": "OK", "predicted": pred, "gold_host_only": "10",
            "correct": pred == "10", "finish_reason": r1["finish_reason"],
            "model_returned": r1["model"],
        }
    except Exception as e:
        events["stages"]["math"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
        STOP_REASON = STOP_REASON or "STAGE_MATH_FAILED"

    # Stage 2: one optimizer mutation
    real_graph = None
    real_prompt_text = None
    if not STOP_REASON:
        try:
            r2 = chat(
                "You are GraphOptimize. Improve a GSM8K math workflow.\n"
                "Return ONLY these XML tags, as short as possible:\n"
                "<modification>one sentence</modification>\n"
                "<graph>class Workflow with async def __call__(self, problem) that calls self.llm; keep it under 25 lines</graph>\n"
                "<prompt>one short instruction string</prompt>\n"
                "graph must compile as Python and define class Workflow.",
                phase="pilot_optimizer",
            )
            parsed = parse_xml(r2["content"])
            events["stages"]["optimizer"] = {"status": "OK", **parsed,
                                             "finish_reason": r2["finish_reason"]}
            if parsed.get("graph") and str(parsed.get("graph_compile", "")).startswith("OK"):
                real_graph = parsed["graph"]
                real_prompt_text = parsed.get("prompt") or ""
            else:
                STOP_REASON = "STRUCTURED_OUTPUT_INCOMPLETE"
        except Exception as e:
            events["stages"]["optimizer"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
            STOP_REASON = STOP_REASON or "STAGE_OPTIMIZER_FAILED"

    # Stage 3: execute the real generated child
    if real_graph and not STOP_REASON:
        try:
            from src.runtime.candidate_bundle import build_bundle

            bundle = build_bundle(graph_src=real_graph, prompt_field=real_prompt_text or "Answer.")
            events["stages"]["bundle"] = {
                "graph_sha": bundle.graph_sha256, "prompt_module_sha": bundle.prompt_module_sha256,
                "bundle_sha": bundle.bundle_sha256, "prompt_contract": bundle.prompt_contract,
            }
            q3 = ("Natalia sold clips to 48 of her friends in April, and then she "
                  "sold half as many clips in May. How many clips did Natalia sell "
                  "altogether in April and May?")

            class PilotIPC:
                def _request(self, prompt: str) -> str:
                    rr = chat(prompt, phase="pilot_workflow_ipc")
                    return rr["content"]

            child = run_workflow_code_isolated(
                real_graph, problem=q3, task_id="gsm8k-train-0000-pilot",
                gold_answer=None, llm=PilotIPC(), timeout=45,
                extra_modules={
                    "prompt": bundle.prompt_module,
                    "workspace.GSM8K.workflows.round_2.prompt": bundle.prompt_module,
                },
            )
            out = child.get("stdout") or ""
            model_text = out
            try:
                payload = json.loads(out[out.find("{"):])
                model_text = payload.get("out", out)
            except Exception:
                pass
            pred3 = extract_num(str(model_text))
            sc = evaluate_workflow_output(
                # gold stays host-side only
                __import__("src.benchmark.gsm8k_tasks", fromlist=["GSM8KTask"]).GSM8KTask(
                    "gsm8k-train-0000-pilot", q3, "72", "#### 72", "search"
                ),
                model_text,
            )
            events["stages"]["child_exec"] = {
                "docker_ok": bool(child.get("ok")),
                "docker_returncode": child.get("returncode"),
                "ipc_processed": len(child.get("ipc_processed") or []),
                "raw_output": str(model_text)[:300],
                "predicted": pred3,
                "gold_host_only": "72",
                "correct": sc.get("correct"),
                "stderr_tail": (child.get("stderr") or "")[-250:],
            }
            if not child.get("ok"):
                STOP_REASON = STOP_REASON or "DOCKER_CHILD_EXECUTION_FAILED"
        except Exception as e:
            events["stages"]["child_exec"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"}
            STOP_REASON = STOP_REASON or "STAGE_CHILD_FAILED"

    # ================= reconciliation =================
    snap = db.snapshot()
    events["REAL_HTTP_REQUESTS"] = snap["physical_attempts"]
    events["LEDGER_REQUESTS"] = len(ledger_rows)
    events["REAL_INPUT_TOKENS"] = snap["actual_tokens_in"]
    events["REAL_OUTPUT_TOKENS"] = snap["actual_tokens_out"]
    events["RESERVED_INPUT_TOKENS"] = snap["reserved_tokens_in"]
    events["RESERVED_OUTPUT_TOKENS"] = snap["reserved_tokens_out"]
    events["BUDGET_DEBITED_USD"] = snap["spent_cost_usd"]
    usage_cost = 0.0
    for r in ledger_rows:
        if r.get("observed_cost_usd"):
            usage_cost += float(r["observed_cost_usd"])
    events["USAGE_COST_ESTIMATE_USD"] = round(usage_cost, 8)
    events["PROVIDER_INVOICE_COST_USD"] = "NOT_VERIFIED"
    events["REAL_API_COST_USD"] = snap["spent_cost_usd"]
    events["BUDGET_REMAINING_USD"] = round(MAX_COST_USD - snap["spent_cost_usd"], 8)
    events["BLOCKED"] = snap["blocked"]
    events["BLOCK_REASON"] = snap["block_reason"]
    events["STOP_REASON"] = STOP_REASON or "PILOT_MINIMAL_SLICE_COMPLETE"
    events["authorization_mode"] = events.get("authorization_mode")

    (OUT / f"pilot_run_{run_id}.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / f"pilot_ledger_{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "rows": ledger_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (OUT / "pilot_latest_summary.json").write_text(
        json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    db.close()

    print(json.dumps({k: events[k] for k in (
        "run_id", "REAL_HTTP_REQUESTS", "REAL_INPUT_TOKENS", "REAL_OUTPUT_TOKENS",
        "REAL_API_COST_USD", "BUDGET_REMAINING_USD", "STOP_REASON",
        "authorization_mode",
    ) if k in events}, indent=2))
    return 0 if not STOP_REASON or STOP_REASON.startswith("PILOT_MINIMAL") else 1


if __name__ == "__main__":
    raise SystemExit(main())
