"""Task E: parent-only re-verification with the fixed scoring adapter.

Re-executes ONLY the parent on the same 12 confirmation tasks. Reuses the
existing frozen child per-task results (no child calls). Max 12 new HTTP.
Full raw responses are saved. No retry. No regeneration of child/task set.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, r"D:/新建文件夹")

from src.runtime.auth_ledger import (
    AuthBudgetLedger,
    AuthorizationMissing,
    AuthorizationRecord,
    UnifiedBudgetGate,
)
from src.runtime.provider_gateway import conservative_input_tokens, worst_case_cost
from src.runtime.workflow_ipc import run_workflow_code_isolated
from src.benchmark.gsm8k_tasks import GSM8KTask

ROOT = Path(r"D:/新建文件夹")
OUT = ROOT / "results" / "level3_pilot_r2"
FROZEN = OUT / "frozen_candidates"

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_IN = 8000
MAX_OUT = 500
MAX_NEW = 12
PRICE_IN = 0.30
PRICE_OUT = 1.20

SECRET = hashlib.sha256(
    (os.environ.get("DEEPSEEK_API_KEY", "") + "|level3-pilot|v1").encode("utf-8")
).hexdigest()

run_id = "parentre-" + uuid.uuid4().hex[:8]
STOP_REASON = ""
EXPECTED_TASK_HASH = "86cc56115220eaede3be4ada49143210ba636d8d3eaf963bf6613c0f67d391b8"
EXPECTED_CHILD_SHA = "a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def normalize_output(raw: Any):
    """Task B normalisation layer: unpack the parent (response, cost) tuple."""
    if isinstance(raw, (tuple, list)) and len(raw) >= 2:
        return str(raw[0]), "TUPLE_UNPACKED", f"cost={raw[1]}"
    s = str(raw)
    import re

    m = re.match(r"^\(\s*['\"](.*)['\"]\s*,\s*[-+eE0-9.]+\s*\)\s*$", s, re.S)
    if m:
        return m.group(1), "TUPLE_REPR_UNPACKED", s[-40:]
    return s, "PLAIN_STRING", ""


def extract_answer(text: str):
    import re

    if not text:
        return None
    if "####" in text:
        tail = text.rsplit("####", 1)[1].strip()
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", tail)
        if m:
            return m.group(0).replace(",", "")
    m = re.search(r"Answer:\s*(-?\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return m.group(1).replace(",", "")
    m = re.search(r"=\s*(-?\d[\d,]*(?:\.\d+)?)\s*[.。]?\s*$", text.strip())
    if m:
        return m.group(1).replace(",", "")
    ms = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)
    return ms[-1].replace(",", "") if ms else None


def main() -> int:
    global STOP_REASON
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY missing")
        return 2

    rec_path = Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json"
    try:
        record = AuthorizationRecord.open_existing(rec_path, secret_key=SECRET)
    except AuthorizationMissing as e:
        print("AUTHORIZATION_MISSING_FAIL_CLOSED", e)
        return 3

    db = AuthBudgetLedger(OUT / f"parentre_budget_{run_id}.sqlite", record)
    gate = UnifiedBudgetGate(db, default_max_in=MAX_IN, default_max_out=MAX_OUT)
    ledger_rows: List[Dict[str, Any]] = []
    n_requests = 0

    def chat(prompt: str, *, phase: str) -> Dict[str, Any]:
        nonlocal n_requests
        global STOP_REASON
        if n_requests >= MAX_NEW:
            STOP_REASON = "NEW_REQUEST_CAP_REACHED"
            raise RuntimeError(STOP_REASON)
        est_in = conservative_input_tokens(prompt)
        reserve_cost = worst_case_cost(MODEL_ID, est_in, MAX_OUT)
        pid = gate.begin_request(
            run_id=run_id, phase=phase, prompt_sha=sha256_text(prompt),
            res_in=est_in, res_out=MAX_OUT, res_cost=reserve_cost,
        )
        n_requests += 1
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        body = json.dumps({
            "model": MODEL_ID, "thinking": {"type": "disabled"},
            "max_tokens": MAX_OUT,
            "messages": [{"role": "user", "content": prompt}],
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}"},
        )
        rec: Dict[str, Any] = {
            "run_id": run_id, "physical_request_id": pid,
            "request_phase": phase, "prompt_sha256": sha256_text(prompt),
        }
        try:
            with opener.open(req, timeout=90) as resp:
                raw = resp.read()
                http_status = int(resp.status)
        except Exception as e:
            rec.update({"error_kind": type(e).__name__, "ledger_status": "fail_closed"})
            gate.complete_unknown(pid, reason=f"{type(e).__name__}:{e}")
            ledger_rows.append(rec)
            STOP_REASON = f"NETWORK:{type(e).__name__}"
            raise
        data = json.loads(raw.decode("utf-8"))
        usage = data.get("usage") or {}
        t_in, t_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        choices = data.get("choices") or []
        finish = choices[0].get("finish_reason") if choices else None
        content = (choices[0].get("message") or {}).get("content") if choices else None
        rec.update({"http_status": http_status, "finish_reason": finish,
                    "usage_prompt_tokens": t_in, "usage_completion_tokens": t_out,
                    "FULL_CONTENT": content})
        if t_in is None or t_out is None:
            gate.complete_unknown(pid, reason="MISSING_USAGE")
            rec["ledger_status"] = "fail_closed"
            ledger_rows.append(rec)
            STOP_REASON = "MISSING_USAGE"
            raise RuntimeError(STOP_REASON)
        cost = (t_in / 1e6) * PRICE_IN + (t_out / 1e6) * PRICE_OUT
        gate.complete_actual(pid, actual_in=int(t_in), actual_out=int(t_out),
                             observed_cost=cost, http_status=http_status,
                             model_returned=data.get("model"), finish_reason=finish)
        rec["observed_cost_usd"] = cost
        rec["ledger_status"] = "settled_ok"
        ledger_rows.append(rec)
        return {"content": content or "", "finish_reason": finish}

    # ---- fixed hashes ----
    conf = json.loads((OUT / "paired_confirmation_set.json").read_text(encoding="utf-8"))
    assert conf["task_set_sha256"] == EXPECTED_TASK_HASH
    child_graph = (FROZEN / "child_graph.py").read_text(encoding="utf-8")
    assert sha256_text(child_graph) == EXPECTED_CHILD_SHA

    # reuse existing child per-task results (no child calls)
    corr_path = OUT / "paired_experiment_results_corrected.json"
    if corr_path.exists():
        corrected = json.loads(corr_path.read_text(encoding="utf-8"))
    else:
        corrected = json.loads((OUT / "paired_experiment_results.json").read_text(encoding="utf-8"))
    child_results = {r["task_id"]: r for r in corrected.get("PER_TASK", []) if r["role"] == "child"}

    parent_graph = (FROZEN / "parent_graph.py").read_text(encoding="utf-8")
    parent_prompt_raw = (FROZEN / "parent_prompt.py").read_text(encoding="utf-8")
    from src.runtime.candidate_bundle import normalize_prompt_module

    parent_prompt_mod = normalize_prompt_module(parent_prompt_raw)

    GENERIC = (
        "class BaseModel:\n    def __init__(self, **kw):\n        pass\n"
        "def Field(default=None, **kw):\n    return default\n"
        "def create_model(name, **kw):\n    return type(name, (BaseModel,), {})\n"
        "def to_jsonable_python(x, **k):\n    return x\n"
        "def __getattr__(name):\n"
        "    if name.startswith('__') and name.endswith('__'):\n        raise AttributeError(name)\n"
        "    return type('_A', (), {'__init__': lambda self,*a,**k: None, '__call__': lambda self,*a,**k: self})()\n"
    )
    AFLOW = ROOT / "external" / "AFlow"
    extras = {
        "pydantic": GENERIC, "pydantic_core": GENERIC,
        "tenacity": "def retry(*a, **k):\n    return lambda f: f\ndef stop_after_attempt(*a, **k):\n    return None\ndef wait_fixed(*a, **k):\n    return None\ndef retry_if_exception_type(*a, **k):\n    return None\n",
        "tree_sitter": "class Node:\n    pass\nclass Parser:\n    pass\nclass Language:\n    pass\n",
        "openai": "class AsyncOpenAI:\n    def __init__(self, *a, **k):\n        pass\nclass OpenAI(AsyncOpenAI):\n    pass\n",
        "yaml": "def safe_load(*a, **k):\n    return {}\n",
        "aiofiles": GENERIC, "numpy": GENERIC, "pandas": GENERIC,
        "httpx": GENERIC, "anyio": GENERIC, "tqdm": GENERIC,
        "tqdm.asyncio": "async def tqdm_asyncio(*a, **k):\n    pass\n",
        "regex": GENERIC, "sympy": GENERIC,
        "sympy.parsing": "", "sympy.parsing.latex": "def parse_latex(*a, **k):\n    return None\n",
        "sympy.parsing.sympy_parser": "def parse_expr(*a, **k):\n    return None\n",
        "typing_extensions": GENERIC, "annotated_types": GENERIC, "pytz": GENERIC,
        "prompt": parent_prompt_mod,
        "workspace.GSM8K.workflows.round_1.prompt": parent_prompt_mod,
    }
    for base in (AFLOW / "workspace", AFLOW / "scripts", AFLOW / "benchmarks"):
        if base.exists():
            for py in base.rglob("*.py"):
                if "__pycache__" in str(py):
                    continue
                rel = py.relative_to(AFLOW)
                dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
                try:
                    extras[dotted] = py.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    parent_rows = []
    for spec in conf["tasks"]:
        if STOP_REASON:
            break
        task = GSM8KTask(spec["task_id"], spec["question"], spec["gold_answer"],
                         f"#### {spec['gold_answer']}", "test")
        entry: Dict[str, Any] = {
            "run_id": run_id, "task_id": task.task_id, "role": "parent",
            "gold_answer": task.gold_answer,
        }
        try:
            class IPC:
                def _request(self, prompt: str) -> str:
                    rr = chat(prompt, phase="parent_ipc")
                    return rr["content"]

            res = run_workflow_code_isolated(
                parent_graph, problem=task.question, task_id=task.task_id,
                gold_answer=None, llm=IPC(), timeout=60, extra_modules=extras,
            )
            out = res.get("stdout") or ""
            # normalisation layer: unpack the parent tuple at the data layer
            model_text = out
            parse_status = "PLAIN_STRING"
            try:
                payload = json.loads(out[out.find("{"):])
                model_text = payload.get("out", out)
            except Exception:
                pass
            text, parse_status, cost_meta = normalize_output(model_text)
            pred = extract_answer(text)
            entry.update({
                "docker_ok": bool(res.get("ok")),
                "ipc_processed": len(res.get("ipc_processed") or []),
                "raw_output_full": text,          # FULL text, not truncated
                "parse_status": parse_status,
                "cost_metadata": cost_meta,
                "predicted": pred,
                "correct": str(pred) == str(task.gold_answer) if pred is not None else False,
            })
        except Exception as e:
            entry.update({"docker_ok": False, "correct": False,
                          "error": f"{type(e).__name__}: {e}"})
        parent_rows.append(entry)
        print(f"parent {task.task_id} pred={entry.get('predicted')} "
              f"gold={task.gold_answer} correct={entry.get('correct')} "
              f"ipc={entry.get('ipc_processed')}")

    # ---- assemble the corrected paired comparison ----
    child_rows = []
    for spec in conf["tasks"]:
        cr = child_results.get(spec["task_id"], {})
        child_rows.append({
            "task_id": spec["task_id"], "role": "child",
            "gold_answer": spec["gold_answer"],
            "predicted": cr.get("predicted_rescored") or cr.get("predicted"),
            "correct": cr.get("correct_rescored") if "correct_rescored" in cr else cr.get("correct"),
            "raw_output_full": cr.get("raw_output"),
            "reused_from": "paired_experiment_results_corrected.json (no new child calls)",
        })

    parent_correct = sum(1 for r in parent_rows if r["correct"])
    child_correct = sum(1 for r in child_rows if r["correct"])
    improved = sum(1 for p, c in zip(parent_rows, child_rows)
                   if not p["correct"] and c["correct"])
    regressed = sum(1 for p, c in zip(parent_rows, child_rows)
                    if p["correct"] and not c["correct"])
    both_correct = sum(1 for p, c in zip(parent_rows, child_rows)
                       if p["correct"] and c["correct"])
    both_wrong = sum(1 for p, c in zip(parent_rows, child_rows)
                     if not p["correct"] and not c["correct"])
    net_gain = child_correct - parent_correct
    assert improved + regressed + both_correct + both_wrong == 12

    snap = db.snapshot()
    parent_cost = sum(r.get("observed_cost_usd") or 0 for r in ledger_rows)

    analysis = {
        "evidence_class": "PARENT_REVERIFICATION (fixed scoring adapter)",
        "run_id": run_id,
        "task_set_sha256": EXPECTED_TASK_HASH,
        "child_graph_sha256": EXPECTED_CHILD_SHA,
        "child_reused_not_recalled": True,
        "PARENT": {
            "correct": parent_correct, "total": 12,
            "accuracy": parent_correct / 12,
            "usage_cost_estimate_usd": round(parent_cost, 8),
            "requests": n_requests,
            "raw_outputs_fully_saved": True,
        },
        "CHILD": {
            "correct": child_correct, "total": 12,
            "accuracy": child_correct / 12,
            "reused": True,
        },
        "PAIRED": {
            "child_improved_over_parent": improved,
            "child_regressed_vs_parent": regressed,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "net_gain": net_gain,
            "total_check": improved + regressed + both_correct + both_wrong,
        },
        "PER_TASK_PARENT": parent_rows,
        "PER_TASK_CHILD": child_rows,
        "NEW_HTTP_REQUESTS": n_requests,
        "BUDGET_DEBITED_USD": snap["spent_cost_usd"],
        "STOP_REASON": STOP_REASON or "PARENT_REVERIFICATION_COMPLETE",
        "caveat": (
            "Child also uses multi-sample self-consistency voting and an explicit "
            "answer format. This is a SYSTEM-LEVEL workflow comparison, not an "
            "isolated attribution to the evolutionary algorithm."
        ),
    }
    (OUT / "parent_reverification_results.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / f"parentre_ledger_{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "rows": ledger_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    db.close()

    print(json.dumps({
        "parent_correct": parent_correct, "child_correct": child_correct,
        "improved": improved, "regressed": regressed,
        "both_correct": both_correct, "both_wrong": both_wrong,
        "net_gain": net_gain,
        "new_requests": n_requests,
        "budget_debited": snap["spent_cost_usd"],
        "STOP_REASON": analysis["STOP_REASON"],
    }, indent=2))
    return 0 if not STOP_REASON or STOP_REASON.startswith("PARENT_REVERIFICATION") else 1


if __name__ == "__main__":
    raise SystemExit(main())
