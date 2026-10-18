"""Re-run paired experiment with parent dependencies properly shipped."""
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
from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output

ROOT = Path(r"D:/新建文件夹")
AFLOW = ROOT / "external" / "AFlow"
OUT = ROOT / "results" / "level3_pilot_r2"
FROZEN = OUT / "frozen_candidates"

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_IN = 8000
MAX_OUT = 500
MAX_NEW_REQUESTS = 100
PRICE_IN = 0.30
PRICE_OUT = 1.20

SECRET = hashlib.sha256(
    (os.environ.get("DEEPSEEK_API_KEY", "") + "|level3-pilot|v1").encode("utf-8")
).hexdigest()

run_id = "paired2-" + uuid.uuid4().hex[:8]
STOP_REASON = ""


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


GENERIC_STUB = (
    "class BaseModel:\n"
    "    def __init__(self, **kw):\n"
    "        pass\n"
    "def Field(default=None, **kw):\n"
    "    return default\n"
    "def create_model(name, **kw):\n"
    "    return type(name, (BaseModel,), {})\n"
    "def to_jsonable_python(x, **k):\n"
    "    return x\n"
    "def __getattr__(name):\n"
    "    if name.startswith('__') and name.endswith('__'):\n"
    "        raise AttributeError(name)\n"
    "    return type('_A', (), {'__init__': lambda self,*a,**k: None, '__call__': lambda self,*a,**k: self})()\n"
)


def collect_modules(prompt_module: str, round_name: str) -> dict:
    mods = {
        "pydantic": GENERIC_STUB,
        "pydantic_core": GENERIC_STUB,
        "tenacity": ("def retry(*a, **k):\n    return lambda f: f\n"
                     "def stop_after_attempt(*a, **k):\n    return None\n"
                     "def wait_fixed(*a, **k):\n    return None\n"
                     "def retry_if_exception_type(*a, **k):\n    return None\n"),
        "tree_sitter": "class Node:\n    pass\nclass Parser:\n    pass\nclass Language:\n    pass\n",
        "openai": "class AsyncOpenAI:\n    def __init__(self, *a, **k):\n        pass\nclass OpenAI(AsyncOpenAI):\n    pass\n",
        "yaml": "def safe_load(*a, **k):\n    return {}\n",
        "aiofiles": GENERIC_STUB,
        "numpy": GENERIC_STUB,
        "pandas": GENERIC_STUB,
        "httpx": GENERIC_STUB,
        "anyio": GENERIC_STUB,
        "tqdm": GENERIC_STUB,
        "tqdm.asyncio": "async def tqdm_asyncio(*a, **k):\n    pass\n",
        "regex": GENERIC_STUB,
        "sympy": GENERIC_STUB,
        "sympy.parsing": "",
        "sympy.parsing.latex": "def parse_latex(*a, **k):\n    return None\n",
        "sympy.parsing.sympy_parser": "def parse_expr(*a, **k):\n    return None\n",
        "typing_extensions": GENERIC_STUB,
        "annotated_types": GENERIC_STUB,
        "pytz": GENERIC_STUB,
        "prompt": prompt_module,
        f"workspace.GSM8K.workflows.{round_name}.prompt": prompt_module,
    }
    for base in (AFLOW / "workspace", AFLOW / "scripts", AFLOW / "benchmarks"):
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            if "__pycache__" in str(py):
                continue
            rel = py.relative_to(AFLOW)
            dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
            try:
                mods[dotted] = py.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
    return mods


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

    db = AuthBudgetLedger(OUT / f"paired_budget_{run_id}.sqlite", record)
    gate = UnifiedBudgetGate(db, default_max_in=MAX_IN, default_max_out=MAX_OUT)
    ledger_rows: List[Dict[str, Any]] = []
    n_requests = 0

    def chat(prompt: str, *, phase: str) -> Dict[str, Any]:
        nonlocal n_requests
        global STOP_REASON
        if n_requests >= MAX_NEW_REQUESTS:
            STOP_REASON = "NEW_REQUEST_CAP_REACHED"
            raise RuntimeError(STOP_REASON)
        est_in = conservative_input_tokens(prompt)
        if est_in > MAX_IN:
            STOP_REASON = "INPUT_TOKEN_CAP_EXCEEDED"
            raise RuntimeError(STOP_REASON)
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
            "estimated_input_tokens": est_in, "reserved_cost_usd": reserve_cost,
        }
        try:
            with opener.open(req, timeout=90) as resp:
                http_status = int(resp.status)
                raw = resp.read()
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
        rec.update({"http_status": http_status, "model_returned": data.get("model"),
                    "finish_reason": finish,
                    "usage_prompt_tokens": t_in, "usage_completion_tokens": t_out})
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

    parent_graph = (FROZEN / "parent_graph.py").read_text(encoding="utf-8")
    child_graph = (FROZEN / "child_graph.py").read_text(encoding="utf-8")
    child_prompt = (FROZEN / "child_prompt.py").read_text(encoding="utf-8")
    parent_prompt_raw = (FROZEN / "parent_prompt.py").read_text(encoding="utf-8")
    # normalize the parent prompt into a module too
    from src.runtime.candidate_bundle import normalize_prompt_module

    parent_prompt_mod = normalize_prompt_module(parent_prompt_raw)

    conf = json.loads((OUT / "paired_confirmation_set.json").read_text(encoding="utf-8"))
    tasks = conf["tasks"]
    assert sha256_text(child_graph) == "a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b"

    results = []
    for spec in tasks:
        task = GSM8KTask(spec["task_id"], spec["question"], spec["gold_answer"],
                         f"#### {spec['gold_answer']}", "test")
        for role, graph_src, extras in (
            ("parent", parent_graph, collect_modules(parent_prompt_mod, "round_1")),
            ("child", child_graph, collect_modules(child_prompt, "round_2")),
        ):
            if STOP_REASON:
                break
            entry: Dict[str, Any] = {
                "run_id": run_id, "task_id": task.task_id, "role": role,
                "graph_sha256": sha256_text(graph_src)[:16],
            }
            try:
                class IPC:
                    def _request(self, prompt: str) -> str:
                        rr = chat(prompt, phase=f"{role}_ipc")
                        return rr["content"]

                child_res = run_workflow_code_isolated(
                    graph_src, problem=task.question, task_id=task.task_id,
                    gold_answer=None, llm=IPC(), timeout=60, extra_modules=extras,
                )
                out = child_res.get("stdout") or ""
                model_text = out
                try:
                    payload = json.loads(out[out.find("{"):])
                    model_text = payload.get("out", out)
                except Exception:
                    pass
                sc = evaluate_workflow_output(task, model_text)
                entry.update({
                    "docker_ok": bool(child_res.get("ok")),
                    "docker_stderr_tail": (child_res.get("stderr") or "")[-200:],
                    "ipc_processed": len(child_res.get("ipc_processed") or []),
                    "predicted": sc.get("predicted"),
                    "correct": bool(sc.get("correct")),
                    "raw_output": str(model_text)[:200],
                })
            except Exception as e:
                entry.update({"docker_ok": False, "correct": False,
                              "error": f"{type(e).__name__}: {e}"})
            results.append(entry)
            print(f"{role} {task.task_id} pred={entry.get('predicted')} "
                  f"gold={task.gold_answer} correct={entry.get('correct')} "
                  f"ipc={entry.get('ipc_processed')} docker={entry.get('docker_ok')}")

    parent = [r for r in results if r["role"] == "parent"]
    child = [r for r in results if r["role"] == "child"]
    parent_correct = sum(1 for r in parent if r.get("correct"))
    child_correct = sum(1 for r in child if r.get("correct"))
    improved = sum(1 for p, c in zip(parent, child)
                   if not p.get("correct") and c.get("correct"))
    regressed = sum(1 for p, c in zip(parent, child)
                    if p.get("correct") and not c.get("correct"))
    tied_correct = sum(1 for p, c in zip(parent, child)
                       if p.get("correct") and c.get("correct"))
    tied_wrong = sum(1 for p, c in zip(parent, child)
                     if not p.get("correct") and not c.get("correct"))

    snap = db.snapshot()
    parent_cost = sum(r.get("observed_cost_usd") or 0 for r in ledger_rows
                      if r.get("request_phase", "").startswith("parent"))
    child_cost = sum(r.get("observed_cost_usd") or 0 for r in ledger_rows
                     if r.get("request_phase", "").startswith("child"))

    analysis = {
        "run_id": run_id,
        "n_tasks": len(tasks),
        "task_set_sha256": conf["task_set_sha256"],
        "child_graph_sha256": "a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b",
        "child_bundle_sha256": "035b51cb257718d8d300ce4793984f8c115ca9efb443f433d01195c94cace173",
        "parent_graph_sha256": hashlib.sha256(parent_graph.encode()).hexdigest(),
        "PARENT": {
            "correct": parent_correct, "total": len(parent),
            "accuracy": parent_correct / len(parent) if parent else 0.0,
            "cost_usd_estimate": round(parent_cost, 8),
            "requests": sum(1 for r in ledger_rows if r.get("request_phase", "").startswith("parent")),
        },
        "CHILD": {
            "correct": child_correct, "total": len(child),
            "accuracy": child_correct / len(child) if child else 0.0,
            "cost_usd_estimate": round(child_cost, 8),
            "requests": sum(1 for r in ledger_rows if r.get("request_phase", "").startswith("child")),
        },
        "PAIRED": {
            "child_improved_over_parent": improved,
            "child_regressed_vs_parent": regressed,
            "both_correct": tied_correct,
            "both_wrong": tied_wrong,
            "net_gain": child_correct - parent_correct,
        },
        "PER_TASK": results,
        "docker_failure_rate": sum(1 for r in results if not r.get("docker_ok")) / max(1, len(results)),
        "ipc_total": sum(int(r.get("ipc_processed") or 0) for r in results),
        "NEW_HTTP_REQUESTS_THIS_RUN": n_requests,
        "BUDGET_DEBITED_USD": snap["spent_cost_usd"],
        "BUDGET_REMAINING_USD": round(5.0 - snap["spent_cost_usd"], 8),
        "STOP_REASON": STOP_REASON or "PAIRED_EXPERIMENT_COMPLETE",
        "exploratory_only": "12 tasks — not statistical significance, not recursive self-improvement proof",
    }

    (OUT / "paired_experiment_results.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / f"paired_ledger_{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "rows": ledger_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    db.close()

    print(json.dumps({
        "parent_acc": analysis["PARENT"]["accuracy"],
        "child_acc": analysis["CHILD"]["accuracy"],
        "improved": improved, "regressed": regressed,
        "net_gain": analysis["PAIRED"]["net_gain"],
        "parent_requests": analysis["PARENT"]["requests"],
        "child_requests": analysis["CHILD"]["requests"],
        "new_requests": n_requests,
        "budget_debited": analysis["BUDGET_DEBITED_USD"],
        "STOP_REASON": analysis["STOP_REASON"],
    }, indent=2))
    return 0 if not STOP_REASON or STOP_REASON.startswith("PAIRED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
