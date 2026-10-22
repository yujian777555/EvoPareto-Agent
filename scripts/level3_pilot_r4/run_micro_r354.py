"""MICRO-R3.5.4 mechanism isolation entry (B/A/O). Offline mock only.

Real mode requires matching authorization; not authorized in this stage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.benchmark.gsm8k_tasks import GSM8KTask, evaluate_workflow_output
from src.research.r3_docker_executor import execute_candidate_docker
from src.research.r3_mutation_feedback import FailureRecord
from src.research.r354_mechanism import (
    BASE_STRATEGY_TEXT,
    PROTOCOL_ID,
    build_append_child,
    build_replace_child,
    diagnosis_from_dev_failures,
    freeze_baseline_b,
)
from src.research.r3_mutation_feedback import hash_program
from src.research.r4_workflow_program import load_frozen_parent
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_PHYSICAL = 150
MAX_COST_USD = 0.15
MAX_IN, MAX_OUT = 1500, 300
SEED = 20260606
FROZEN = ROOT / "results/level3_pilot_r2" / "frozen_candidates"
TS = ROOT / "results/level3_pilot_r4_micro_r354"


class Budget:
    def __init__(self):
        self.n = 0
        self.cost = 0.0
        self.tok_in = 0
        self.tok_out = 0
        self.rows: List[Dict[str, Any]] = []
        self.stop: Optional[str] = None

    def precheck(self, est_in: int) -> str:
        if self.stop:
            return self.stop
        if self.n >= MAX_PHYSICAL:
            self.stop = "INCOMPLETE_BUDGET_STOP"
            return self.stop
        reserve = worst_case_cost(MODEL_ID, min(est_in, MAX_IN), MAX_OUT)
        if self.cost + reserve > MAX_COST_USD + 1e-12:
            self.stop = "INCOMPLETE_BUDGET_STOP"
            return self.stop
        return ""

    def add(self, row):
        self.rows.append(row)
        self.n += 1
        if row.get("settle") == "fail_closed_unknown" or (row.get("cost_usd") is None and row.get("error")):
            self.stop = "INCOMPLETE_BUDGET_STOP"
        self.cost += float(row.get("cost_usd") or 0)
        self.tok_in += int(row.get("tokens_in") or 0)
        self.tok_out += int(row.get("tokens_out") or 0)

    def dump(self):
        unsettled = sum(1 for r in self.rows if r.get("settle") == "fail_closed_unknown" or r.get("cost_usd") is None)
        return {
            "n_physical_requests": self.n,
            "known_cost_usd": round(self.cost, 8),
            "unsettled_request_count": unsettled,
            "cost_final": unsettled == 0,
            "total_cost_usd": round(self.cost, 8) if unsettled == 0 else None,
            "stop_reason": self.stop,
            "max_physical": MAX_PHYSICAL,
            "max_cost_usd": MAX_COST_USD,
            "requests": self.rows,
        }


class Mailbox:
    def __init__(self, budget, task_id, phase, mock, mock_mode):
        self.budget, self.task_id, self.phase = budget, task_id, phase
        self.mock, self.mock_mode = mock, mock_mode

    def _request(self, prompt: str) -> str:
        if self.mock_mode:
            if self.mock is None:
                raise RuntimeError("FIXTURE_NOT_CONFIGURED")
            return self.mock
        est = conservative_input_tokens(str(prompt))
        err = self.budget.precheck(est)
        if err:
            raise RuntimeError(err)
        body = json.dumps({
            "model": MODEL_ID, "thinking": {"type": "disabled"}, "max_tokens": MAX_OUT,
            "messages": [{"role": "user", "content": str(prompt)[: MAX_IN * 3]}],
        }).encode("utf-8")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        req = urllib.request.Request(
            f"{BASE_URL}/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
        )
        row = {"phase": self.phase, "task_id": self.task_id,
               "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest(),
               "estimated_input_tokens": est}
        t0 = time.time()
        try:
            with opener.open(req, timeout=90) as resp:
                raw = resp.read()
                row["http_status"] = int(resp.status)
            row["latency_s"] = round(time.time() - t0, 3)
        except Exception as e:
            row.update({"error": f"{type(e).__name__}:{e}", "cost_usd": None, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            row.update({"error": f"JSON:{type(e).__name__}", "cost_usd": None, "settle": "fail_closed_unknown"})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        usage = data.get("usage") or {}
        t_in, t_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if t_in is None or t_out is None:
            row.update({"error": "USAGE_MISSING", "cost_usd": None, "settle": "fail_closed_unknown"})
            self.budget.add(row)
            raise RuntimeError("USAGE_MISSING")
        content = ""
        ch = data.get("choices") or []
        if ch:
            content = (ch[0].get("message") or {}).get("content") or ""
        try:
            cost = estimate_cost(MODEL_ID, int(t_in), int(t_out), peak=True)
        except Exception as e:
            row.update({"error": f"COST:{type(e).__name__}", "cost_usd": None, "settle": "fail_closed_unknown"})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        row.update({"tokens_in": int(t_in), "tokens_out": int(t_out), "cost_usd": cost, "settle": "settled_actual", "http_sent": True})
        self.budget.add(row)
        return content

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def to_task(t):
    return GSM8KTask(t["task_id"], t["question"], t["gold_answer"], f"#### {t['gold_answer']}", "train")


def classify_execution(row) -> str:
    """Strict taxonomy: valid answer error vs parse vs execution vs skip."""
    if row.get("skipped"):
        return "SKIPPED"
    if row.get("error"):
        return "EXECUTION_ERROR"
    if row.get("executed_graph_source") is not True:
        return "EXECUTION_ERROR"
    if row.get("graph_sha256_match") is not True:
        return "EXECUTION_ERROR"
    if row.get("ok") is not True:
        return "EXECUTION_ERROR"
    if row.get("predicted") in (None, ""):
        return "PARSE_ERROR"
    return "ANSWER_MISMATCH" if not row.get("correct") else "NO_FAILURE"


def is_valid_eval(row) -> bool:
    """True only if execution evidence and parse are good enough for accuracy."""
    return (
        not row.get("skipped")
        and row.get("executed_graph_source") is True
        and row.get("graph_sha256_match") is True
        and row.get("ok") is True
        and row.get("predicted") not in (None, "")
    )


def run_arm(prog, tasks, budget, phase, mock_mode, fixtures=None):
    fixtures = fixtures or {}
    rows = []
    if getattr(budget, "stop", None):
        return [{"task_id": t.task_id, "skipped": True, "skip_reason": budget.stop,
                 "correct": None, "valid_eval": False} for t in tasks]
    for i, t in enumerate(tasks):
        if getattr(budget, "stop", None):
            rows.extend([{"task_id": x.task_id, "skipped": True, "skip_reason": budget.stop,
                          "correct": None, "valid_eval": False} for x in tasks[i:]])
            break
        mock = fixtures.get(t.task_id, "Compute. Answer: 12345" if mock_mode else None)
        box = Mailbox(budget, t.task_id, phase, mock, mock_mode)
        try:
            r = execute_candidate_docker(prog, t.question, llm=box, task_id=t.task_id, expect_graph_sha256=hash_program(prog))
        except Exception as e:
            r = {"ok": False, "error": str(e), "answer_text": None, "executed_graph_source": False,
                 "graph_sha256_match": False, "n_llm_calls": 1}
        sc = evaluate_workflow_output(t, r.get("answer_text") or "")
        valid = (
            not r.get("error")
            and r.get("executed_graph_source") is True
            and r.get("graph_sha256_match") is True
            and r.get("ok") is True
            and sc.get("predicted") not in (None, "")
        )
        rows.append({
            "task_id": t.task_id, "program_id": r.get("program_id"),
            "graph_sha256": r.get("graph_sha256"), "graph_sha256_match": r.get("graph_sha256_match"),
            "executed_graph_source": r.get("executed_graph_source"), "ok": r.get("ok"),
            "n_llm_calls": r.get("n_llm_calls"), "predicted": sc.get("predicted"),
            "correct": bool(sc.get("correct")) if valid else None,
            "valid_eval": valid,
            "exec_class": None,  # filled below
            "error": r.get("error"), "phase": phase,
        })
        rows[-1]["exec_class"] = classify_execution(rows[-1])
    return rows


def classify_row(row) -> str:
    """One authoritative classification for every evaluation row."""
    if row is None:
        return "MISSING"
    if row.get("skipped"):
        return "SKIPPED"
    err = (row.get("error") or "").strip()
    if err:
        # execution failure beats any success-looking fields
        return "EXEC_FAILURE"
    if row.get("graph_hash_mismatch") or row.get("hash_mismatch"):
        return "HASH_MISMATCH"
    if row.get("predicted") is None or row.get("predicted") == "":
        return "PARSE_FAILURE"
    if row.get("valid_eval") is False:
        return "INVALID"
    if row.get("correct") is True:
        return "CORRECT"
    return "WRONG_ANSWER"


def is_valid_eval(row) -> bool:
    """Strict: only fully executed, hash-matched, parseable rows count."""
    return classify_row(row) in ("CORRECT", "WRONG_ANSWER")


def acc(rows, expected_n=None):
    """Strict accuracy. Returns None unless every expected row is valid.

    - rows: list of evaluation records
    - expected_n: required task count (default len(rows))
    Invalid / skipped / failed / unparseable -> None (NOT counted as wrong).
    """
    if not rows:
        return None
    if expected_n is not None and len(rows) != expected_n:
        return None
    classes = [classify_row(r) for r in rows]
    if any(c not in ("CORRECT", "WRONG_ANSWER") for c in classes):
        return None
    return sum(1 for c in classes if c == "CORRECT") / len(rows)


def paired(a_rows, b_rows):
    """COMPLETE only if both arms fully valid and task_ids match 1-1."""
    if len(a_rows) != len(b_rows):
        return {"status": "INCOMPLETE", "reason": "LENGTH_MISMATCH", "n_a": len(a_rows), "n_b": len(b_rows)}
    ids_a = [r.get("task_id") for r in a_rows]
    ids_b = [r.get("task_id") for r in b_rows]
    if ids_a != ids_b:
        return {"status": "INCOMPLETE", "reason": "TASK_ID_MISMATCH",
                "ids_a": ids_a[:10], "ids_b": ids_b[:10]}
    if any(not is_valid_eval(r) for r in a_rows + b_rows):
        invalid = [r.get("task_id") for r in list(a_rows) + list(b_rows) if not is_valid_eval(r)]
        return {"status": "INCOMPLETE", "reason": "INVALID_OR_MISSING_EVAL", "invalid_tasks": invalid[:10]}
    imp = reg = both_c = both_w = 0
    for a, b in zip(a_rows, b_rows):
        if b["correct"] and not a["correct"]:
            imp += 1
        elif a["correct"] and not b["correct"]:
            reg += 1
        elif a["correct"]:
            both_c += 1
        else:
            both_w += 1
    n = imp + reg
    p = 1.0 if n == 0 else min(1.0, 2 * sum(__import__("math").comb(n, i) for i in range(0, min(imp, reg) + 1)) / (2 ** n))
    return {"improved": imp, "regressed": reg, "both_correct": both_c, "both_wrong": both_w,
            "mcnemar_exact_p_two_sided": p, "n": len(a_rows), "status": "COMPLETE"}


def build_feedback_records(B, dev_tasks, b_dev):
    """Only valid, hash-matched, executed rows may drive ANSWER_MISMATCH feedback."""
    out = []
    for t, r in zip(dev_tasks, b_dev):
        cls = classify_execution(r)
        out.append(FailureRecord(
            task_id=t.task_id, parent_program_id=B.program_id,
            parent_graph_sha256=hash_program(B),
            success=bool(r.get("valid_eval") and r.get("correct")),
            error_category=cls if cls != "NO_FAILURE" else "NO_FAILURE",
            predicted=r.get("predicted"), gold=t.gold_answer,
            diagnosis_uses_gold=True,
            diagnostic=f"valid_eval={r.get('valid_eval')} sha={r.get('graph_sha256_match')} err={r.get('error')}",
        ))
    return out


def preflight_runtime(man, ts, baseline_freeze, a_rec, o_rec):
    """Recompute everything before any HTTP. Returns list of errors."""
    import hashlib as _h

    errors = []
    train = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
    if _h.sha256(train.read_bytes()).hexdigest() != man.get("train_sha256"):
        errors.append("TRAIN_SHA_MISMATCH")

    def content_sha(block):
        blob = json.dumps(
            [(t["task_id"], " ".join(t["question"].split()), t["gold_answer"]) for t in block["tasks"]],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return _h.sha256(blob.encode("utf-8")).hexdigest()

    for role, key in (("calibration", "calib_task_set_sha256"), ("dev", "dev_task_set_sha256"), ("confirm", "confirm_task_set_sha256")):
        if content_sha(ts[role]) != man.get(key):
            errors.append(f"{role.upper()}_SHA_MISMATCH")
        nkey = {"calibration": "n_calib", "dev": "n_dev", "confirm": "n_confirm"}[role]
        if len(ts[role]["tasks"]) != man.get(nkey):
            errors.append(f"{role.upper()}_COUNT_MISMATCH")
        ids = [t["task_id"] for t in ts[role]["tasks"]]
        idxs = ts[role].get("indices") or []
        if len(ids) != len(idxs):
            errors.append(f"{role.upper()}_INDEX_LEN")
        for tid, idx, task in zip(ids, idxs, ts[role]["tasks"]):
            if tid != f"gsm8k-train-{idx:04d}":
                errors.append(f"{role.upper()}_ID_INDEX:{tid}")
    sets = [set(ts[r]["indices"]) for r in ("calibration", "dev", "confirm")]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        errors.append("SETS_OVERLAP")
    used = set(man.get("used_indices_excluded") or [])
    for s in sets:
        if s & used:
            errors.append("HISTORICAL_REUSE")
    if baseline_freeze.get("base_text") != BASE_STRATEGY_TEXT:
        errors.append("BASELINE_TEXT_MISMATCH")
    if not baseline_freeze.get("base_text_sha256"):
        errors.append("BASELINE_SHA_MISSING")
    fb_a = a_rec.get("feedback_text_used") if a_rec else None
    fb_o = o_rec.get("feedback_text_used") if o_rec else None
    if a_rec and o_rec and fb_a != fb_o:
        errors.append("A_O_FEEDBACK_TEXT_MISMATCH")
    return errors


def holm_adjust(pvals: Dict[str, float]) -> Dict[str, Dict[str, float]]:
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    out = {}
    running = 0.0
    for i, (name, p) in enumerate(items):
        adj = min(1.0, max(running, (m - i) * p))
        running = adj
        out[name] = {"p_raw": p, "p_holm": adj, "reject_0_05": adj <= 0.05}
    return out


def check_ao_consistency(B, A, O, a_rec, o_rec, diag):
    """A/O must share identical feedback; traceable Dev-only source; valid lineage."""
    errors = []
    fb_a = a_rec.get("feedback_text_used") if a_rec else None
    fb_o = o_rec.get("feedback_text_used") if o_rec else None
    if fb_a != fb_o:
        errors.append("A_O_FEEDBACK_TEXT_MISMATCH")
    id_a = a_rec.get("feedback_id") if a_rec else None
    id_o = o_rec.get("feedback_id") if o_rec else None
    if id_a != id_o:
        errors.append("A_O_FEEDBACK_ID_MISMATCH")
    if diag is not None:
        src = set(diag.source_task_ids) if hasattr(diag, "source_task_ids") else set()
        rec_src = set(a_rec.get("source_task_ids") or [])
        if not rec_src <= src:
            errors.append("FEEDBACK_SOURCE_NOT_FROM_DEV")
    # lineage: A/O must record parent
    if a_rec.get("parent_id") != "B" and a_rec.get("parent") != "B":
        errors.append("A_PARENT_NOT_B")
    if o_rec.get("parent_id") != "B" and o_rec.get("parent") != "B":
        errors.append("O_PARENT_NOT_B")
    return errors


def preflight_static(man, ts, baseline_freeze):
    """Static checks that MUST run before any HTTP / model call.

    Recomputes hashes from actual text; checks set integrity, base strategy
    SHA from re-computation, protocol version, output dir, budget init.
    """
    import hashlib as _h
    errors = []
    # protocol / model / freeze files
    if baseline_freeze.get("protocol_id") != PROTOCOL_ID and man.get("protocol_id") != PROTOCOL_ID:
        errors.append("PROTOCOL_ID_MISMATCH")
    if not (ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl").exists():
        errors.append("TRAIN_FILE_MISSING")
        return errors
    train = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
    if _h.sha256(train.read_bytes()).hexdigest() != man.get("train_sha256"):
        errors.append("TRAIN_SHA_MISMATCH")

    def content_sha(block):
        blob = json.dumps(
            [(t["task_id"], " ".join(t["question"].split()), t["gold_answer"]) for t in block["tasks"]],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return _h.sha256(blob.encode("utf-8")).hexdigest()

    for role, key in (("calibration", "calib_task_set_sha256"), ("dev", "dev_task_set_sha256"), ("confirm", "confirm_task_set_sha256")):
        if content_sha(ts[role]) != man.get(key):
            errors.append(f"{role.upper()}_SHA_MISMATCH")
        nkey = {"calibration": "n_calib", "dev": "n_dev", "confirm": "n_confirm"}[role]
        if len(ts[role]["tasks"]) != man.get(nkey):
            errors.append(f"{role.upper()}_COUNT_MISMATCH")
        ids = [t["task_id"] for t in ts[role]["tasks"]]
        idxs = ts[role].get("indices") or []
        if len(ids) != len(idxs):
            errors.append(f"{role.upper()}_INDEX_LEN")
        for tid, idx in zip(ids, idxs):
            if tid != f"gsm8k-train-{idx:04d}":
                errors.append(f"{role.upper()}_ID_INDEX:{tid}")
    sets = [set(ts[r]["indices"]) for r in ("calibration", "dev", "confirm")]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        errors.append("SETS_OVERLAP")
    used = set(man.get("used_indices_excluded") or [])
    for s in sets:
        if s & used:
            errors.append("HISTORICAL_REUSE")
    # R1.1: recompute base strategy SHA from actual text (not just field non-empty)
    recomputed = _h.sha256(BASE_STRATEGY_TEXT.encode("utf-8")).hexdigest()
    if baseline_freeze.get("base_text") != BASE_STRATEGY_TEXT:
        errors.append("BASELINE_TEXT_MISMATCH")
    recorded = baseline_freeze.get("base_text_sha256") or man.get("base_text_sha256")
    if not recorded:
        errors.append("BASELINE_SHA_MISSING")
    elif recorded != recomputed:
        errors.append("BASELINE_SHA_RECOMPUTE_MISMATCH")
    return errors


def check_real_authorization(man, baseline_freeze):
    """Fail-closed real-mode authorization. Never auto-creates records."""
    errors = []
    auth_path = ROOT / "results/level3_pilot_r4_micro_r354/authorization.json"
    if not auth_path.exists():
        return ["AUTH_MISSING"]
    try:
        auth = json.loads(auth_path.read_text(encoding="utf-8"))
    except Exception:
        return ["AUTH_UNREADABLE"]
    required = ["protocol_id", "model_id", "confirm_sha256", "code_version",
                "max_requests", "max_cost_usd", "status"]
    for f in required:
        if f not in auth:
            errors.append(f"AUTH_FIELD_MISSING:{f}")
    if auth.get("protocol_id") != PROTOCOL_ID:
        errors.append("AUTH_PROTOCOL_MISMATCH")
    if auth.get("model_id") != MODEL_ID:
        errors.append("AUTH_MODEL_MISMATCH")
    if auth.get("confirm_sha256") != man.get("confirm_task_set_sha256"):
        errors.append("AUTH_CONFIRM_SHA_MISMATCH")
    if auth.get("status") not in ("active", "approved"):
        errors.append("AUTH_STATUS_NOT_ACTIVE")
    if auth.get("max_requests", 0) > MAX_PHYSICAL:
        errors.append("AUTH_REQUEST_CAP_TOO_HIGH")
    if auth.get("max_cost_usd", 0) > MAX_COST_USD + 1e-12:
        errors.append("AUTH_COST_CAP_TOO_HIGH")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=str(TS / "live_r354"))
    args = ap.parse_args()
    # R1.1: real-mode entry is gated by check_real_authorization (see below).
    ts = json.loads((TS / "taskset_r354.json").read_text(encoding="utf-8"))
    man = json.loads((TS / "taskset_r354_manifest.json").read_text(encoding="utf-8"))
    calib = [to_task(t) for t in ts["calibration"]["tasks"]]
    dev_tasks = [to_task(t) for t in ts["dev"]["tasks"]]
    conf_tasks = [to_task(t) for t in ts["confirm"]["tasks"]]
    if args.smoke:
        calib, dev_tasks, conf_tasks = calib[:2], dev_tasks[:2], conf_tasks[:2]

    parent = load_frozen_parent(FROZEN)
    base_pack = freeze_baseline_b(parent)
    B = base_pack["program"]
    budget = Budget()
    outdir = Path(args.out)
    if outdir.exists() and any(outdir.iterdir()):
        print(f"BLOCKED: output dir not empty: {outdir}")
        return 4

    # R1.1: STATIC PREFLIGHT must pass before ANY request (incl. mock accounting)
    static_errors = preflight_static(man, ts, base_pack["freeze"])
    if static_errors:
        print("STATIC_PREFLIGHT_FAILED: " + ";".join(static_errors))
        return 5  # zero HTTP, no fabricated results

    # R1.1: real-mode authorization gate (fail-closed). Real mode NOT executed this round.
    if not args.mock:
        auth_errors = check_real_authorization(man, base_pack["freeze"])
        if auth_errors:
            print("AUTH_GATE_BLOCKED: " + ";".join(auth_errors))
            return 6
        # Even with auth, this entry remains blocked pending Planner approval.
        print("BLOCKED: real execution requires Planner authorization for MICRO-R3.5.4-MECHANISM-ISOLATION-v1")
        return 3

    outdir.mkdir(parents=True, exist_ok=True)

    # Dev B to generate real failures (feedback source only)
    b_dev = run_arm(B, dev_tasks, budget, "dev:B", args.mock)
    fails = build_feedback_records(B, dev_tasks, b_dev)
    # only ANSWER_MISMATCH-class records may drive answer-feedback mutation
    answer_fails = [f for f in fails if f.error_category == "ANSWER_MISMATCH" and not f.success]
    diag = diagnosis_from_dev_failures(answer_fails) if answer_fails else None
    feedback_label = diag.coarse_label if diag else None
    feedback_id = diag.feedback_id if diag else None
    src_ids = list(diag.source_task_ids) if diag else []

    # A and O from SAME feedback text
    a_out = build_append_child(B, feedback_label or "NO_FAILURE", feedback_id=feedback_id or "NONE", source_task_ids=src_ids) if diag else {"child": None, "record": {"status": "NO_USABLE_FEEDBACK", "reason": "NO_DEV_FAILURES"}}
    o_out = build_replace_child(B, feedback_label or "NO_FAILURE", feedback_id=feedback_id or "NONE", source_task_ids=src_ids) if diag else {"child": None, "record": {"status": "NO_USABLE_FEEDBACK", "reason": "NO_DEV_FAILURES"}}
    A, O = a_out["child"], o_out["child"]

    # R1.1: B2 — A/O consistency gate BEFORE confirm-set evaluation
    if diag is None or A is None or O is None:
        # NO_USABLE_FEEDBACK: do not fabricate A/O, do not waste confirm budget
        summary = {
            "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
            "protocol": PROTOCOL_ID,
            "status": "INCOMPLETE",
            "incomplete_reason": "NO_USABLE_FEEDBACK",
            "experiment_complete": False,
            "preflight_errors": [],
            "budget": budget.dump(),
        }
        (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("NO_USABLE_FEEDBACK: skipping confirm evaluation")
        return 7

    ao_errors = check_ao_consistency(B, A, O, a_out.get("record", {}), o_out.get("record", {}), diag)
    if ao_errors:
        summary = {
            "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
            "protocol": PROTOCOL_ID,
            "status": "INCOMPLETE",
            "incomplete_reason": "AO_INCONSISTENT",
            "ao_errors": ao_errors,
            "experiment_complete": False,
            "preflight_errors": [],
            "budget": budget.dump(),
        }
        (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("AO_INCONSISTENT: " + ";".join(ao_errors))
        return 8

    arms = {"B": B, "A": A, "O": O}
    conf = {name: run_arm(prog, conf_tasks, budget, f"conf:{name}", args.mock) for name, prog in arms.items()}

    # R1.1: use module-level strict acc(); no local override
    analysis = {}
    if "B" in conf and "A" in conf:
        analysis["A_vs_B"] = paired(conf["B"], conf["A"])
    if "B" in conf and "O" in conf:
        analysis["O_vs_B"] = paired(conf["B"], conf["O"])
    if "A" in conf and "O" in conf:
        analysis["A_vs_O"] = paired(conf["O"], conf["A"])
    pvals = {k: v["mcnemar_exact_p_two_sided"] for k, v in analysis.items() if v.get("status") == "COMPLETE"}
    REQUIRED_COMPS = ("A_vs_B", "O_vs_B", "A_vs_O")
    missing_comps = [k for k in REQUIRED_COMPS if k not in pvals]
    holm = holm_adjust(pvals) if pvals else {}
    holm_complete = len(missing_comps) == 0
    if not holm_complete:
        holm["_incomplete"] = {"missing": missing_comps,
                               "note": "MULTIPLE_COMPARISONS_INCOMPLETE"}

    # strict complete: all required arms, all valid evals, settled costs, complete stats
    required_arms = {"B", "A", "O"}
    arms_ok = required_arms.issubset(set(conf.keys()))
    all_valid = all(all(r.get("valid_eval") for r in rows) for rows in conf.values()) if conf else False
    stats_ok = all(v.get("status") == "COMPLETE" for v in analysis.values()) if analysis else False
    settled = budget.dump().get("cost_final") is True
    complete = arms_ok and all_valid and stats_ok and settled and budget.stop is None and holm_complete
    incomplete_reason = None
    if not complete:
        reasons = []
        if not arms_ok:
            reasons.append("MISSING_ARMS")
        if not all_valid:
            reasons.append("INVALID_EVALS")
        if not stats_ok:
            reasons.append("INCOMPLETE_STATS")
        if not settled:
            reasons.append("UNSETTLED_COST")
        if not holm_complete:
            reasons.append("MULTIPLE_COMPARISONS_INCOMPLETE")
        if budget.stop:
            reasons.append(str(budget.stop))
        incomplete_reason = ";".join(reasons)

    # R1.1: consistency checks after feedback construction (already gated before confirm)
    preflight_errors = preflight_runtime(man, ts, base_pack["freeze"], a_out.get("record") if isinstance(a_out, dict) else None, o_out.get("record") if isinstance(o_out, dict) else None)

    summary = {
        "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
        "preflight_errors": preflight_errors,
        "protocol": PROTOCOL_ID,
        "seed": SEED,
        "taskset_sha256": {k: man[k] for k in ("calib_task_set_sha256", "dev_task_set_sha256", "confirm_task_set_sha256")},
        "n_calib": len(calib), "n_dev": len(dev_tasks), "n_confirm": len(conf_tasks),
        "baseline_b": base_pack["freeze"],
        "feedback_label": feedback_label,
        "feedback_id": feedback_id,
        "feedback_source_task_ids": src_ids,
        "a_record": a_out["record"],
        "o_record": o_out["record"],
        "a_vs_o_same_feedback_text": a_out["record"].get("feedback_text_used") == o_out["record"].get("feedback_text_used"),
        "confirm_accuracy": {k: acc(v) for k, v in conf.items()},
        "paired_analysis": analysis,
        "holm_adjusted": holm,
        "multiplicity": "Holm over {A_vs_B, O_vs_B, A_vs_O} task-level McNemar",
        "statistical_unit": "task-level paired (n=confirm); seed-level not run this stage",
        "requests_total": budget.n,
        "known_cost_usd": round(budget.cost, 8),
        "cost_final": budget.dump()["cost_final"],
        "calibration_status": "NOT_EXECUTED_IN_ENTRY",
        "calibration_note": "calib tasks frozen for future use; entry runs dev-feedback only; request budget excludes calib",
        "experiment_complete": complete,
        "incomplete_reason": incomplete_reason,
        "confirm_used_for_selection": False,
        "statistical_claim": "EXPLORATORY_ONLY",
    }
    lineage = {
        "B": base_pack["freeze"],
        "A": a_out["record"],
        "O": o_out["record"],
    }
    (outdir / "protocol.json").write_text(json.dumps({**man, "model": MODEL_ID, "arms": list(arms)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "candidate_lineage.json").write_text(json.dumps(lineage, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (outdir / "failure_archive.json").write_text(json.dumps({"dev_B": [f.to_dict() for f in fails]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_results.json").write_text(json.dumps({"dev_B": b_dev, "confirm": conf}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_analysis.json").write_text(json.dumps({"paired": analysis, "holm": holm}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "request_ledger.json").write_text(json.dumps(budget.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "REPORT.md").write_text(
        f"# MICRO-R3.5.4 mechanism isolation\n\nMode: **{'SIMULATED' if args.mock else 'REAL'}**\n\n"
        f"- B base text sha={base_pack['freeze']['base_text_sha256'][:16]}…\n"
        f"- feedback={feedback_label} id={feedback_id} src={src_ids}\n"
        f"- A/O same text={summary['a_vs_o_same_feedback_text']}\n"
        f"- confirm={summary['confirm_accuracy']}\n- paired={json.dumps(analysis, sort_keys=True)}\n"
        f"- holm={json.dumps(holm, sort_keys=True)}\n\n**Exploratory. Not RSI proof.**\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
