"""MICRO-R3.5 real-run entry (5 arms). Offline mock only until authorized.

Arms: P, R (random), F_old (R3.4 OP_ARITH_RECHECK), F_local (append), E2_local.
E2 uses the gen-1 winner's OWN dev FailureRecords via generate_e2_from_winner.
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
from src.research.r3_mutation_feedback import (
    FailureRecord,
    apply_random_mutation,
    build_feedback_child,
    hash_program,
    summarize_feedback,
)
from src.research.r35_f_local import apply_f_local, build_feedback_diagnosis, generate_e2_from_winner
from src.research.r4_workflow_program import load_frozen_parent
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

MODEL_ID = "deepseek-flash"
EXPERIMENT_PROTOCOL_ID = "MICRO-R3.5-EXP-v1"
CODE_REVISION = "r3.5.3-planner-fix1"
BASE_URL = "https://api.deepseek.com"
MAX_PHYSICAL = 300
MAX_COST_USD = 0.30
MAX_IN, MAX_OUT = 1500, 300
SEED = 20260605
FROZEN = ROOT / "results/level3_pilot_r2" / "frozen_candidates"
TS = ROOT / "results/level3_pilot_r4_micro_r35"


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
            self.stop = "REQUEST_CAP_REACHED"
            return self.stop
        reserve = worst_case_cost(MODEL_ID, min(est_in, MAX_IN), MAX_OUT)
        if self.cost + reserve > MAX_COST_USD + 1e-12:
            self.stop = "COST_RESERVE_EXCEEDED"
            return self.stop
        return ""

    def add(self, row):
        self.rows.append(row)
        self.n += 1
        settle = str(row.get("settle") or "")
        if settle == "fail_closed_unknown" or row.get("cost_usd") is None:
            self.stop = "INCOMPLETE_BUDGET_STOP"
        if self.stop and self.stop.startswith("REQUEST_CAP"):
            self.stop = "INCOMPLETE_BUDGET_STOP"
        self.cost += float(row.get("cost_usd") or 0)
        self.tok_in += int(row.get("tokens_in") or 0)
        self.tok_out += int(row.get("tokens_out") or 0)
        if self.n >= MAX_PHYSICAL:
            self.stop = self.stop or "INCOMPLETE_BUDGET_STOP"

    def dump(self):
        unsettled = sum(1 for r in self.rows if r.get("settle") == "fail_closed_unknown" or r.get("cost_usd") is None)
        return {
            "evidence_class": "R35_LEDGER",
            "n_physical_requests": self.n,
            "known_cost_usd": round(self.cost, 8),
            "unsettled_request_count": unsettled,
            "cost_final": unsettled == 0,
            "total_cost_usd": round(self.cost, 8) if unsettled == 0 else None,
            "total_cost_note": "UNKNOWN_UNSETTLED" if unsettled else "FINAL",
            "tokens_in": self.tok_in,
            "tokens_out": self.tok_out,
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
            row.update({"error": f"{type(e).__name__}:{e}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception as e:
            # HTTP was sent but body unusable -> physical request recorded, unsettled, stop
            row.update({"error": f"JSON:{type(e).__name__}", "cost_usd": None, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown", "http_sent": True})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        usage = data.get("usage") or {}
        t_in, t_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if t_in is None or t_out is None:
            row.update({"error": "USAGE_MISSING", "cost_usd": None, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown", "http_sent": True})
            self.budget.add(row)
            raise RuntimeError("USAGE_MISSING")
        t_in, t_out = int(t_in), int(t_out)
        content = ""
        ch = data.get("choices") or []
        if ch:
            content = (ch[0].get("message") or {}).get("content") or ""
        try:
            cost = estimate_cost(MODEL_ID, t_in, t_out, peak=True)
        except Exception as e:
            row.update({"error": f"COST:{type(e).__name__}", "cost_usd": None, "tokens_in": t_in, "tokens_out": t_out, "settle": "fail_closed_unknown", "http_sent": True})
            self.budget.add(row)
            raise RuntimeError(row["error"])
        row.update({"tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost, "settle": "settled_actual", "usage_raw": usage, "http_sent": True})
        self.budget.add(row)
        return content

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def to_task(t):
    return GSM8KTask(t["task_id"], t["question"], t["gold_answer"], f"#### {t['gold_answer']}", "train")


def _skipped_rows(tasks, reason):
    return [
        {
            "task_id": t.task_id,
            "skipped": True,
            "skip_reason": reason,
            "correct": None,
            "counts_toward_accuracy": False,
        }
        for t in tasks
    ]


def run_arm(prog, tasks, budget, phase, mock_mode, fixtures=None):
    fixtures = fixtures or {}
    rows = []
    if getattr(budget, "stop", None):
        return _skipped_rows(tasks, budget.stop)

    for i, t in enumerate(tasks):
        if getattr(budget, "stop", None):
            rows.extend(_skipped_rows(tasks[i:], budget.stop))
            break

        mock = fixtures.get(t.task_id, "Compute. Answer: 12345" if mock_mode else None)
        box = Mailbox(budget, t.task_id, phase, mock, mock_mode)
        try:
            r = execute_candidate_docker(prog, t.question, llm=box, task_id=t.task_id, expect_graph_sha256=hash_program(prog))
        except Exception as e:
            r = {"ok": False, "error": str(e), "answer_text": None, "executed_graph_source": False, "n_llm_calls": 1}
        sc = evaluate_workflow_output(t, r.get("answer_text") or "")
        valid_execution = (
            r.get("error") in (None, "")
            and r.get("ok") is True
            and r.get("executed_graph_source") is True
            and r.get("graph_sha256_match") is True
        )
        rows.append({
            "task_id": t.task_id, "program_id": r.get("program_id"),
            "graph_sha256": r.get("graph_sha256"), "graph_sha256_match": r.get("graph_sha256_match"),
            "executed_graph_source": r.get("executed_graph_source"), "ok": r.get("ok"),
            "n_llm_calls": r.get("n_llm_calls"), "predicted": sc.get("predicted"),
            "correct": bool(sc.get("correct")), "error": r.get("error"), "phase": phase,
            "skipped": False, "counts_toward_accuracy": valid_execution,
        })

        # Infrastructure/evidence failures invalidate the arm and stop further spend.
        if not valid_execution and not getattr(budget, "stop", None):
            budget.stop = "EXECUTION_ERROR_STOP"

        # A stop triggered during this task must prevent all later task executions.
        if getattr(budget, "stop", None) and i + 1 < len(tasks):
            rows.extend(_skipped_rows(tasks[i + 1:], budget.stop))
            break
    return rows


def classify_row(row) -> str:
    """Strict failure taxonomy (R3.5.2).

    ANSWER_MISMATCH only if execution chain was valid, graph hash matched,
    and an answer was parsed. Budget stop / container fail / no answer must
    not masquerade as ordinary answer errors.
    """
    if row.get("error"):
        err = str(row["error"])
        if "BUDGET" in err or "REQUEST_CAP" in err or "COST_RESERVE" in err or "INCOMPLETE_BUDGET" in err:
            return "EXECUTION_ERROR"
        return "EXECUTION_ERROR"
    if not row.get("executed_graph_source"):
        return "EXECUTION_ERROR"
    if row.get("graph_sha256_match") is not True:
        # missing or false both fail the evidence bar
        return "EXECUTION_ERROR"
    if row.get("ok") is not True:
        return "EXECUTION_ERROR"
    if row.get("predicted") in (None, ""):
        return "PARSE_ERROR"
    return "ANSWER_MISMATCH" if not row.get("correct") else "NO_FAILURE"


def fails_from(prog, tasks, rows):
    out = []
    for t, r in zip(tasks, rows):
        # Skipped/incomplete rows are not failures and cannot drive feedback.
        if r.get("skipped") or r.get("counts_toward_accuracy") is False:
            continue
        cat = classify_row(r)
        out.append(FailureRecord(
            task_id=t.task_id, parent_program_id=prog.program_id,
            parent_graph_sha256=r.get("graph_sha256") or hash_program(prog),
            success=bool(r.get("correct")),
            error_category=cat,
            predicted=r.get("predicted"), gold=t.gold_answer,
            diagnosis_uses_gold=True,
            diagnostic=f"executed={r.get('executed_graph_source')} sha_match={r.get('graph_sha256_match')} ok={r.get('ok')} err={r.get('error')}",
        ))
    return out


def accuracy(rows):
    """Return accuracy only for a complete set of valid execution rows."""
    if not rows:
        return None
    if any(
        row.get("skipped")
        or row.get("counts_toward_accuracy") is False
        or "correct" not in row
        or not isinstance(row.get("correct"), bool)
        for row in rows
    ):
        return None
    return sum(1 for row in rows if row["correct"]) / len(rows)


def paired(a_rows, b_rows):
    if len(a_rows) != len(b_rows) or accuracy(a_rows) is None or accuracy(b_rows) is None:
        return {
            "status": "INCOMPLETE",
            "reason": "MISSING_OR_INVALID_PAIRED_ROWS",
            "n_a": len(a_rows),
            "n_b": len(b_rows),
        }
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
    return {"status": "COMPLETE", "improved": imp, "regressed": reg, "both_correct": both_c, "both_wrong": both_w,
            "mcnemar_exact_p_two_sided": p, "n": len(a_rows)}


AUTH_PATH_ENV = "EVOPARETO_R35_EXEC_AUTH"
AUTH_PATH_DEFAULT = Path.home() / ".evopareto" / "state" / "r35_execution_authorization.json"


def preflight_verify(man: dict, ts: dict) -> dict:
    """Recompute task hashes from content; verify counts, disjointness, source."""
    import hashlib as _h

    errors = []
    train = ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl"
    train_sha = _h.sha256(train.read_bytes()).hexdigest()
    if train_sha != man.get("train_sha256"):
        errors.append("TRAIN_SHA_MISMATCH")

    def content_sha(block):
        items = block["tasks"]
        blob = json.dumps(
            [(t["task_id"], " ".join(t["question"].split()), t["gold_answer"]) for t in items],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return _h.sha256(blob.encode("utf-8")).hexdigest()

    dev_sha = content_sha(ts["dev"])
    conf_sha = content_sha(ts["confirm"])
    if dev_sha != man.get("dev_task_set_sha256"):
        errors.append("DEV_SHA_MISMATCH")
    if conf_sha != man.get("confirm_task_set_sha256"):
        errors.append("CONFIRM_SHA_MISMATCH")
    if len(ts["dev"]["tasks"]) != man.get("n_dev"):
        errors.append("DEV_COUNT_MISMATCH")
    if len(ts["confirm"]["tasks"]) != man.get("n_confirm"):
        errors.append("CONFIRM_COUNT_MISMATCH")
    di = {t["task_id"] for t in ts["dev"]["tasks"]}
    ci = {t["task_id"] for t in ts["confirm"]["tasks"]}
    if di & ci:
        errors.append("DEV_CONFIRM_OVERLAP")
    used = set(man.get("used_indices_excluded") or [])
    for block in (ts["dev"], ts["confirm"]):
        if set(block["indices"]) & used:
            errors.append("HISTORICAL_INDEX_REUSE")
    # index <-> task_id <-> official content mapping
    official = {}
    with train.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = " ".join((ans.rsplit("####", 1)[-1] if "####" in ans else ans).strip().split())
            official[i] = (" ".join(o["question"].split()), gold)
    for block_name in ("dev", "confirm"):
        block = ts[block_name]
        ids = [t["task_id"] for t in block["tasks"]]
        idxs = block.get("indices") or []
        if len(ids) != len(idxs):
            errors.append(f"{block_name.upper()}_INDEX_TASK_COUNT_MISMATCH")
        for tid, idx, task in zip(ids, idxs, block["tasks"]):
            if type(idx) is not int:
                errors.append(f"{block_name.upper()}_INDEX_TYPE_INVALID:{tid}")
                continue
            expected_id = f"gsm8k-train-{idx:04d}"
            if tid != expected_id:
                errors.append(f"{block_name.upper()}_TASK_ID_INDEX_MISMATCH:{tid}")
            if idx not in official:
                errors.append(f"{block_name.upper()}_INDEX_NOT_IN_TRAIN:{idx}")
                continue
            oq, og = official[idx]
            if " ".join(task["question"].split()) != oq or task["gold_answer"] != og:
                errors.append(f"{block_name.upper()}_CONTENT_MISMATCH:{tid}")
        valid_indices = [idx for idx in idxs if type(idx) is int]
        if len(valid_indices) != len(set(valid_indices)):
            errors.append(f"{block_name.upper()}_DUPLICATE_INDICES")
        # historical exclusion must use real indices
        real_idxs = set(idxs)
        if real_idxs & used:
            errors.append(f"{block_name.upper()}_HISTORICAL_INDEX_REUSE")
    # parent frozen hash
    try:
        from src.research.r4_workflow_program import PARENT_GRAPH_LF_SHA256, program_provenance

        pg = load_frozen_parent(FROZEN)
        if program_provenance(pg)["graph_sha256"] != PARENT_GRAPH_LF_SHA256:
            errors.append("PARENT_GRAPH_SHA_MISMATCH")
    except Exception as e:
        errors.append(f"PARENT_LOAD:{type(e).__name__}")
    return {"errors": errors, "dev_sha": dev_sha, "confirm_sha": conf_sha, "train_sha": train_sha}


def verify_execution_authorization(
    *,
    protocol: str,
    model: str,
    confirm_sha: str,
    max_requests: int,
    max_cost_usd: float,
    code_revision: str | None = None,
) -> str:
    """Fail-closed authorization. protocol is experiment id; code_revision is separate."""
    import os as _os

    path = Path(_os.environ.get(AUTH_PATH_ENV) or AUTH_PATH_DEFAULT)
    if not path.exists():
        return "EXEC_AUTH_FILE_MISSING"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return f"EXEC_AUTH_PARSE:{type(e).__name__}"
    required = {
        "status": "AUTHORIZED",
        "protocol": protocol,
        "model": model,
        "confirm_task_set_sha256": confirm_sha,
        "max_requests": max_requests,
        "max_cost_usd": max_cost_usd,
    }
    if code_revision is not None:
        required["code_revision"] = code_revision
    for k, v in required.items():
        if raw.get(k) != v:
            return f"EXEC_AUTH_FIELD_MISMATCH:{k}"
    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="limit to 2 dev + 2 confirm offline smoke")
    ap.add_argument("--out", default=str(TS / "live_r35"))
    args = ap.parse_args()
    if not args.mock and not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2

    ts = json.loads((TS / "taskset_r35.json").read_text(encoding="utf-8"))
    man = json.loads((TS / "taskset_r35_manifest.json").read_text(encoding="utf-8"))
    dev_tasks = [to_task(t) for t in ts["dev"]["tasks"]]
    conf_tasks = [to_task(t) for t in ts["confirm"]["tasks"]]
    if args.smoke:
        dev_tasks = dev_tasks[:2]
        conf_tasks = conf_tasks[:2]

    # Order: preflight -> auth -> output dir -> experiment
    ver = preflight_verify(man, ts)
    if ver["errors"]:
        print("PREFLIGHT_FAILED:", ver["errors"])
        return 5
    parent = load_frozen_parent(FROZEN)
    if not args.mock:
        auth_err = verify_execution_authorization(
            protocol=EXPERIMENT_PROTOCOL_ID,
            code_revision=CODE_REVISION,
            model=MODEL_ID,
            confirm_sha=man["confirm_task_set_sha256"],
            max_requests=MAX_PHYSICAL,
            max_cost_usd=MAX_COST_USD,
        )
        if auth_err:
            print("BLOCKED:", auth_err)
            return 3
    budget = Budget()
    outdir = Path(args.out)
    if outdir.exists() and any(outdir.iterdir()):
        print(f"BLOCKED: output directory not empty: {outdir}")
        return 4
    outdir.mkdir(parents=True, exist_ok=True)

    completed_stages = []

    # Dev P
    p_dev = run_arm(parent, dev_tasks, budget, "dev:P", args.mock)
    if accuracy(p_dev) is not None:
        completed_stages.append("dev_parent")
    p_fails = fails_from(parent, dev_tasks, p_dev)
    parent_diag = build_feedback_diagnosis([f for f in p_fails if not f.success])

    # Gen1 candidates
    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
    # F_old: R3.4-style feedback child (OP_ARITH_RECHECK path)
    f_old, rec_f_old = build_feedback_child(parent, summarize_feedback(p_fails), seed=SEED, slot=2)
    # F_local
    f_local, rec_f_local = (None, {"status": "NO_USABLE_FEEDBACK"})
    if parent_diag:
        fl = apply_f_local(parent, parent_diag)
        f_local, rec_f_local = fl["child"], fl["record"]

    arms_g1 = {"P": (parent, p_dev), "R": (child_r, []), "F_old": (f_old, []), "F_local": (f_local, [])}
    dev_rows = {"P": p_dev}
    for name in ("R", "F_old", "F_local"):
        prog = arms_g1[name][0]
        if prog:
            dev_rows[name] = run_arm(prog, dev_tasks, budget, f"dev:{name}", args.mock)
        else:
            dev_rows[name] = []

    gen1_names = [name for name in ("R", "F_old", "F_local") if arms_g1[name][0]]
    scores = {}
    if not budget.stop and accuracy(p_dev) is not None and gen1_names and all(
        accuracy(dev_rows.get(name, [])) is not None for name in gen1_names
    ):
        scores = {name: accuracy(dev_rows[name]) for name in gen1_names}
        completed_stages.append("dev_gen1")
    order = [k for k in ("R", "F_old", "F_local") if k in scores]
    winner_name = max(order, key=lambda n: (scores[n], -order.index(n))) if order else None
    winner = {"R": child_r, "F_old": f_old, "F_local": f_local}.get(winner_name)
    winner_rows = dev_rows.get(winner_name, [])
    winner_fails = fails_from(winner, dev_tasks, winner_rows) if winner else []

    e2_out = generate_e2_from_winner(winner, winner_fails) if winner else {
        "child": None, "record": {"status": "NOT_GENERATED_NO_FAILURE", "reason": "NO_WINNER"}
    }
    e2, rec_e2 = e2_out["child"], e2_out["record"]
    e2_rows = run_arm(e2, dev_tasks, budget, "dev:E2_local", args.mock) if e2 else []
    if e2 and accuracy(e2_rows) is not None:
        completed_stages.append("dev_gen2")

    # Confirm — all arms with a program
    arms = {}
    for name, prog in (("P", parent), ("R", child_r), ("F_old", f_old), ("F_local", f_local), ("E2_local", e2)):
        if prog:
            arms[name] = prog
    conf = {n: run_arm(p, conf_tasks, budget, f"conf:{n}", args.mock) for n, p in arms.items()}

    if not budget.stop and conf and all(accuracy(rows) is not None for rows in conf.values()):
        completed_stages.append("confirm")

    analysis = {}
    base = conf["P"]
    for n in conf:
        if n != "P":
            analysis[f"P_vs_{n}"] = paired(base, conf[n])
    if "R" in conf and "F_local" in conf:
        analysis["F_local_vs_R"] = paired(conf["R"], conf["F_local"])
    if "F_old" in conf and "F_local" in conf:
        analysis["F_local_vs_F_old"] = paired(conf["F_old"], conf["F_local"])
    if e2 and winner_name in conf and "E2_local" in conf:
        analysis[f"E2_local_vs_{winner_name}"] = paired(conf[winner_name], conf["E2_local"])

    required_eval_sets = [p_dev]
    required_eval_sets.extend(dev_rows[name] for name in gen1_names)
    if e2:
        required_eval_sets.append(e2_rows)
    required_eval_sets.extend(conf.values())
    invalid_execution_rows = any(accuracy(rows) is None for rows in required_eval_sets)
    incomplete = budget.stop is not None or invalid_execution_rows
    incomplete_reason = budget.stop or ("INVALID_OR_INCOMPLETE_EXECUTION_ROWS" if invalid_execution_rows else None)
    analysis_out = {"note": "INCOMPLETE_NO_FULL_STATS"} if incomplete else analysis
    summary = {
        "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
        "experiment_complete": not incomplete,
        "incomplete_reason": incomplete_reason,
        "completed_stages": completed_stages,
        "protocol": EXPERIMENT_PROTOCOL_ID,
        "code_revision": CODE_REVISION,
        "seed": SEED,
        "taskset_sha256": {"dev": man["dev_task_set_sha256"], "confirm": man["confirm_task_set_sha256"]},
        "n_dev": len(dev_tasks), "n_confirm": len(conf_tasks),
        "dev_scores": scores,
        "gen1_winner": winner_name,
        "f_old_status": rec_f_old.get("status") if isinstance(rec_f_old, dict) else None,
        "f_local_status": rec_f_local.get("status"),
        "e2_status": rec_e2.get("status"),
        "e2_reason": rec_e2.get("reason"),
        "e2_feedback_from": rec_e2.get("e2_feedback_from"),
        "e2_source_task_ids": rec_e2.get("e2_source_task_ids"),
        "e2_generation": e2.generation if e2 else None,
        "e2_parent_ok": (e2.parent_program_id == winner.program_id) if e2 and winner else False,
        "confirm_accuracy": {k: accuracy(v) for k, v in conf.items()},
        "paired_analysis": analysis_out,
        "requests_total": budget.n,
        "known_cost_usd": budget.dump()["known_cost_usd"],
        "unsettled_request_count": budget.dump()["unsettled_request_count"],
        "cost_final": budget.dump()["cost_final"],
        "cost_usd_total": budget.dump()["total_cost_usd"],
        "stop_reason": budget.stop,
        "budget": {"max_physical": MAX_PHYSICAL, "max_cost_usd": MAX_COST_USD},
        "confirm_used_for_selection": False,
        "statistical_claim": ("SIMULATED_INCOMPLETE" if incomplete else "SIMULATED_ONLY") if args.mock else ("INCOMPLETE" if incomplete else "EXPLORATORY_ONLY"),
    }
    lineage = {
        "P": {"program_id": parent.program_id, "graph_sha256": hash_program(parent), "generation": 0},
        "R": rec_r, "F_old": rec_f_old, "F_local": rec_f_local, "E2_local": rec_e2,
        "winner": {"arm": winner_name, "program_id": winner.program_id if winner else None},
    }
    (outdir / "protocol.json").write_text(json.dumps({**man, "model": MODEL_ID, "protocol_id": EXPERIMENT_PROTOCOL_ID, "code_revision": CODE_REVISION, "arms": list(arms)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "candidate_lineage.json").write_text(json.dumps(lineage, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (outdir / "failure_archive.json").write_text(json.dumps({
        "parent_dev": [f.to_dict() for f in p_fails],
        "winner_dev": [f.to_dict() for f in winner_fails],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_results.json").write_text(json.dumps({"dev": dev_rows, "confirm": conf}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_analysis.json").write_text(json.dumps(analysis_out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "request_ledger.json").write_text(json.dumps(budget.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    ledger_summary = budget.dump()
    if ledger_summary["cost_final"]:
        cost_text = f"${ledger_summary['total_cost_usd']:.6f} (final)"
    else:
        cost_text = f"UNKNOWN; known subtotal=${ledger_summary['known_cost_usd']:.6f}; unsettled={ledger_summary['unsettled_request_count']}"
    (outdir / "REPORT.md").write_text(
        f"# {EXPERIMENT_PROTOCOL_ID} / {CODE_REVISION}\n\nMode: **{'SIMULATED' if args.mock else 'REAL'}**\n\n"
        f"- requests={budget.n} cost={cost_text}\n- experiment_complete={summary['experiment_complete']} reason={summary['incomplete_reason']}\n"
        f"- winner={winner_name} scores={scores}\n"
        f"- E2: {summary['e2_status']} from={summary['e2_feedback_from']} src={summary['e2_source_task_ids']}\n"
        f"- confirm={summary['confirm_accuracy']}\n\n**Not RSI proof.**\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
