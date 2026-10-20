"""LEVEL3-PILOT-R3: 35-question parent-child paired experiment (real DeepSeek)."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
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
OUT = ROOT / "results" / "level3_pilot_r3"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_IN = 8000
MAX_OUT = 500
MAX_NEW = 175
PRICE_IN = 0.30
PRICE_OUT = 1.20

SECRET = hashlib.sha256(
    (os.environ.get("DEEPSEEK_API_KEY", "") + "|level3-pilot|v1").encode("utf-8")
).hexdigest()

EXPECTED_PARENT_SHA = "ee6cde435b71893e424d96b39a10afac125c221f7d5f631d1510f40998f93d8e"
EXPECTED_CHILD_SHA = "a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b"
EXPECTED_BUNDLE_SHA = "035b51cb257718d8d300ce4793984f8c115ca9efb443f433d01195c94cace173"
EXPECTED_TASK_HASH = "ddf055537d4618c8"  # will be verified in full

run_id = "r3-" + uuid.uuid4().hex[:8]
STOP_REASON = ""


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def main() -> int:
    global STOP_REASON
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        print("DEEPSEEK_API_KEY missing")
        return 2

    # authorization
    rec_path = Path.home() / ".evopareto" / "state" / "level3_pilot_authorization.json"
    try:
        record = AuthorizationRecord.open_existing(rec_path, secret_key=SECRET)
    except AuthorizationMissing as e:
        print("AUTHORIZATION_MISSING_FAIL_CLOSED", e)
        return 3

    snap0 = record.snapshot_flat()
    remaining_req = snap0["max_physical"] - snap0["physical_attempts"]
    if remaining_req < 175:
        print(f"INSUFFICIENT_REQUEST_BUDGET:{remaining_req}<175")
        return 3
    if snap0.get("blocked"):
        print("BUDGET_BLOCKED", snap0.get("block_reason"))
        return 3

    db = AuthBudgetLedger(OUT / f"r3_budget_{run_id}.sqlite", record)
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
            "estimated_input_tokens": est_in, "reserved_cost_usd": reserve_cost,
        }
        try:
            t0 = time.time()
            with opener.open(req, timeout=90) as resp:
                raw = resp.read()
                http_status = int(resp.status)
            rec["latency_s"] = round(time.time() - t0, 3)
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
        rec.update({
            "http_status": http_status, "model_returned": data.get("model"),
            "finish_reason": finish,
            "usage_prompt_tokens": t_in, "usage_completion_tokens": t_out,
            "FULL_CONTENT": content,
        })
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
        return {"content": content or "", "finish_reason": finish, "cost": cost}

    # load frozen artifacts
    parent_graph = (FROZEN / "parent_graph.py").read_text(encoding="utf-8")
    child_graph = (FROZEN / "child_graph.py").read_text(encoding="utf-8")
    child_prompt = (FROZEN / "child_prompt.py").read_text(encoding="utf-8")
    parent_prompt_raw = (FROZEN / "parent_prompt.py").read_text(encoding="utf-8")
    from src.runtime.candidate_bundle import normalize_prompt_module

    parent_prompt_mod = normalize_prompt_module(parent_prompt_raw)

    # verify hashes (text-normalized for graph)
    child_bytes = (FROZEN / "child_graph.py").read_bytes()
    child_byte_sha = hashlib.sha256(child_bytes).hexdigest()
    child_lf_sha = hashlib.sha256(child_bytes.replace(b"\r\n", b"\n")).hexdigest()
    if child_lf_sha != EXPECTED_CHILD_SHA and child_byte_sha != EXPECTED_CHILD_SHA:
        print(f"CHILD_SHA_MISMATCH:byte={child_byte_sha[:16]} lf={child_lf_sha[:16]}")
        return 3
    parent_bytes = (FROZEN / "parent_graph.py").read_bytes()
    parent_byte_sha = hashlib.sha256(parent_bytes).hexdigest()
    parent_lf_sha = hashlib.sha256(parent_bytes.replace(b"\r\n", b"\n")).hexdigest()
    if parent_byte_sha != EXPECTED_PARENT_SHA and parent_lf_sha != EXPECTED_PARENT_SHA:
        print(f"PARENT_SHA_MISMATCH:byte={parent_byte_sha[:16]} lf={parent_lf_sha[:16]}")
        return 3

    conf = json.loads((OUT / "paired_confirmation_set_35.json").read_text(encoding="utf-8"))
    tasks_data = conf["tasks"]
    if len(tasks_data) != 35:
        print(f"TASK_COUNT_MISMATCH:{len(tasks_data)}")
        return 3
    task_blob = json.dumps(
        [(t["task_id"], t["question"], t["gold_answer"]) for t in tasks_data],
        sort_keys=True,
    )
    recomputed_hash = hashlib.sha256(task_blob.encode("utf-8")).hexdigest()
    declared_hash = conf.get("task_set_sha256", "")
    if recomputed_hash != declared_hash:
        print(f"TASK_SET_HASH_MISMATCH:recomputed={recomputed_hash[:16]} declared={declared_hash[:16]}")
        return 3
    tids = [t["task_id"] for t in tasks_data]
    if len(set(tids)) != len(tids):
        print("TASK_ID_DUPLICATE")
        return 3
    if tids != sorted(tids):
        print("TASK_ORDER_MISMATCH")
        return 3

    # dependency stubs for Docker
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
    base_extras = {
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
    }
    for base in (AFLOW / "workspace", AFLOW / "scripts", AFLOW / "benchmarks"):
        if base.exists():
            for py in base.rglob("*.py"):
                if "__pycache__" in str(py):
                    continue
                rel = py.relative_to(AFLOW)
                dotted = str(rel.with_suffix("")).replace("\\", "/").replace("/", ".")
                try:
                    base_extras[dotted] = py.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    parent_extras = dict(base_extras)
    parent_extras["prompt"] = parent_prompt_mod
    parent_extras["workspace.GSM8K.workflows.round_1.prompt"] = parent_prompt_mod
    child_extras = dict(base_extras)
    child_extras["prompt"] = child_prompt
    child_extras["workspace.GSM8K.workflows.round_2.prompt"] = child_prompt

    results = []
    order = []  # balanced parent/child ordering
    for i, spec in enumerate(tasks_data):
        if i % 2 == 0:
            order.extend([("parent", spec), ("child", spec)])
        else:
            order.extend([("child", spec), ("parent", spec)])

    for role, spec in order:
        if STOP_REASON:
            break
        task = GSM8KTask(spec["task_id"], spec["question"], spec["gold_answer"],
                         f"#### {spec['gold_answer']}", "test")
        graph_src = parent_graph if role == "parent" else child_graph
        extras = parent_extras if role == "parent" else child_extras
        entry: Dict[str, Any] = {
            "run_id": run_id, "task_id": task.task_id, "role": role,
            "gold_answer": task.gold_answer,
            "graph_sha256": sha256_text(graph_src),
        }
        t_start = time.time()
        try:
            class IPC:
                def _request(self, prompt: str) -> str:
                    rr = chat(prompt, phase=f"{role}_ipc")
                    return rr["content"]

            res = run_workflow_code_isolated(
                graph_src, problem=task.question, task_id=task.task_id,
                gold_answer=None, llm=IPC(), timeout=60, extra_modules=extras,
            )
            entry["latency_s"] = round(time.time() - t_start, 3)
            out = res.get("answer_text") or ""
            model_text = out
            try:
                payload = json.loads(out[out.find("{"):]) if "{" in out else {}
                model_text = payload.get("answer_text", payload.get("out", out))
            except Exception:
                pass
            sc = evaluate_workflow_output(task, model_text)
            entry.update({
                "docker_ok": bool(res.get("ok")),
                "docker_cleanup": res.get("docker_cleanup"),
                "ipc_processed": len(res.get("ipc_processed") or []),
                "predicted": sc.get("predicted"),
                "correct": bool(sc.get("correct")),
                "raw_output_full": str(model_text)[:500],
                "answer_sha256": res.get("answer_sha256"),
            })
        except Exception as e:
            entry.update({"docker_ok": False, "correct": False, "latency_s": round(time.time() - t_start, 3),
                          "error": f"{type(e).__name__}: {e}"})
        results.append(entry)
        print(f"{role} {task.task_id} pred={entry.get('predicted')} gold={task.gold_answer} "
              f"correct={entry.get('correct')} ipc={entry.get('ipc_processed')} "
              f"lat={entry.get('latency_s')}s")

    # analysis
    parent = [r for r in results if r["role"] == "parent"]
    child = [r for r in results if r["role"] == "child"]
    pc = sum(1 for r in parent if r["correct"])
    cc = sum(1 for r in child if r["correct"])
    improved = sum(1 for p, c in zip(parent, child) if not p["correct"] and c["correct"])
    regressed = sum(1 for p, c in zip(parent, child) if p["correct"] and not c["correct"])
    both_ok = sum(1 for p, c in zip(parent, child) if p["correct"] and c["correct"])
    both_bad = sum(1 for p, c in zip(parent, child) if not p["correct"] and not c["correct"])
    net = cc - pc

    # McNemar exact test
    from math import comb
    b, c = improved, regressed
    n_pairs = b + c
    mcnemar_p = 1.0 if n_pairs == 0 else sum(comb(n_pairs, k) for k in range(min(b, c) + 1)) / (2 ** n_pairs)

    snap = db.snapshot()
    parent_cost = sum(r.get("observed_cost_usd") or 0 for r in ledger_rows if r.get("request_phase", "").startswith("parent"))
    child_cost = sum(r.get("observed_cost_usd") or 0 for r in ledger_rows if r.get("request_phase", "").startswith("child"))

    analysis = {
        "run_id": run_id,
        "n_tasks": 35,
        "task_set_sha256": conf.get("task_set_sha256"),
        "child_graph_sha256": EXPECTED_CHILD_SHA,
        "parent_graph_sha256": EXPECTED_PARENT_SHA,
        "PARENT": {"correct": pc, "total": 35, "accuracy": pc / 35,
                    "cost_usd_estimate": round(parent_cost, 8),
                    "requests": sum(1 for r in ledger_rows if r.get("request_phase", "").startswith("parent"))},
        "CHILD": {"correct": cc, "total": 35, "accuracy": cc / 35,
                   "cost_usd_estimate": round(child_cost, 8),
                   "requests": sum(1 for r in ledger_rows if r.get("request_phase", "").startswith("child"))},
        "PAIRED": {
            "child_improved_over_parent": improved,
            "child_regressed_vs_parent": regressed,
            "both_correct": both_ok,
            "both_wrong": both_bad,
            "net_gain": net,
            "mcnemar_exact_p": round(mcnemar_p, 6),
            "discordant_pairs": n_pairs,
        },
        "PER_TASK": results,
        "docker_failure_rate": sum(1 for r in results if not r.get("docker_ok")) / max(1, len(results)),
        "ipc_total": sum(int(r.get("ipc_processed") or 0) for r in results),
        "NEW_HTTP_REQUESTS": n_requests,
        "BUDGET_DEBITED_USD": snap["spent_cost_usd"],
        "BUDGET_REMAINING_USD": round(5.0 - snap["spent_cost_usd"], 8),
        "STOP_REASON": STOP_REASON or "R3_PAIRED_EXPERIMENT_COMPLETE",
        "exploratory_note": (
            "35-task paired comparison. Child uses multi-sample self-consistency "
            "and explicit answer format — system-level workflow comparison, not "
            "isolated evolutionary algorithm attribution."
        ),
    }
    (OUT / "paired_experiment_results.json").write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (OUT / f"r3_ledger_{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "rows": ledger_rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    db.close()

    print(json.dumps({
        "parent_acc": analysis["PARENT"]["accuracy"], "child_acc": analysis["CHILD"]["accuracy"],
        "improved": improved, "regressed": regressed,
        "both_ok": both_ok, "both_bad": both_bad, "net_gain": net,
        "mcnemar_p": round(mcnemar_p, 6),
        "new_requests": n_requests,
        "budget_debited": snap["spent_cost_usd"],
        "STOP_REASON": analysis["STOP_REASON"],
    }, indent=2))
    return 0 if not STOP_REASON or STOP_REASON.startswith("R3") else 1


if __name__ == "__main__":
    raise SystemExit(main())
