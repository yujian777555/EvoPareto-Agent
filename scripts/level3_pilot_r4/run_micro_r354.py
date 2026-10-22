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
MAX_PHYSICAL = 400
MAX_COST_USD = 0.35
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


def run_arm(prog, tasks, budget, phase, mock_mode, fixtures=None):
    fixtures = fixtures or {}
    rows = []
    if getattr(budget, "stop", None):
        return [{"task_id": t.task_id, "skipped": True, "skip_reason": budget.stop,
                 "correct": False, "counts_toward_accuracy": False} for t in tasks]
    for i, t in enumerate(tasks):
        if getattr(budget, "stop", None):
            rows.extend([{"task_id": x.task_id, "skipped": True, "skip_reason": budget.stop,
                          "correct": False, "counts_toward_accuracy": False} for x in tasks[i:]])
            break
        mock = fixtures.get(t.task_id, "Compute. Answer: 12345" if mock_mode else None)
        box = Mailbox(budget, t.task_id, phase, mock, mock_mode)
        try:
            r = execute_candidate_docker(prog, t.question, llm=box, task_id=t.task_id, expect_graph_sha256=hash_program(prog))
        except Exception as e:
            r = {"ok": False, "error": str(e), "answer_text": None, "executed_graph_source": False, "n_llm_calls": 1}
        sc = evaluate_workflow_output(t, r.get("answer_text") or "")
        rows.append({
            "task_id": t.task_id, "program_id": r.get("program_id"),
            "graph_sha256": r.get("graph_sha256"), "graph_sha256_match": r.get("graph_sha256_match"),
            "executed_graph_source": r.get("executed_graph_source"), "ok": r.get("ok"),
            "n_llm_calls": r.get("n_llm_calls"), "predicted": sc.get("predicted"),
            "correct": bool(sc.get("correct")), "error": r.get("error"), "phase": phase,
        })
    return rows


def paired(a_rows, b_rows):
    if len(a_rows) != len(b_rows):
        return {"status": "INCOMPLETE", "reason": "LENGTH_MISMATCH"}
    imp = reg = both_c = both_w = 0
    for a, b in zip(a_rows, b_rows):
        if a.get("skipped") or b.get("skipped"):
            return {"status": "INCOMPLETE", "reason": "SKIPPED_ROWS"}
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=str(TS / "live_r354"))
    args = ap.parse_args()
    if not args.mock:
        print("BLOCKED: real execution requires new authorization for MICRO-R3.5.4")
        return 3

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
    outdir.mkdir(parents=True, exist_ok=True)

    # Dev B to generate real failures (feedback source only)
    b_dev = run_arm(B, dev_tasks, budget, "dev:B", args.mock)
    fails = [
        FailureRecord(
            task_id=t.task_id, parent_program_id=B.program_id,
            parent_graph_sha256=hash_program(B), success=bool(r.get("correct")),
            error_category="ANSWER_MISMATCH" if (r.get("executed_graph_source") and r.get("graph_sha256_match") and r.get("predicted")) and not r.get("correct") else ("EXECUTION_ERROR" if r.get("error") or not r.get("executed_graph_source") else "PARSE_ERROR"),
            predicted=r.get("predicted"), gold=t.gold_answer, diagnosis_uses_gold=True,
        )
        for t, r in zip(dev_tasks, b_dev)
    ]
    diag = diagnosis_from_dev_failures(fails)
    feedback_label = diag.coarse_label if diag else None
    feedback_id = diag.feedback_id if diag else None
    src_ids = list(diag.source_task_ids) if diag else []

    # A and O from SAME feedback text
    a_out = build_append_child(B, feedback_label or "NO_FAILURE", feedback_id=feedback_id or "NONE", source_task_ids=src_ids) if diag else {"child": None, "record": {"status": "NO_USABLE_FEEDBACK", "reason": "NO_DEV_FAILURES"}}
    o_out = build_replace_child(B, feedback_label or "NO_FAILURE", feedback_id=feedback_id or "NONE", source_task_ids=src_ids) if diag else {"child": None, "record": {"status": "NO_USABLE_FEEDBACK", "reason": "NO_DEV_FAILURES"}}
    A, O = a_out["child"], o_out["child"]

    arms = {"B": B}
    if A:
        arms["A"] = A
    if O:
        arms["O"] = O
    conf = {name: run_arm(prog, conf_tasks, budget, f"conf:{name}", args.mock) for name, prog in arms.items()}

    def acc(rows):
        valid = [r for r in rows if not r.get("skipped")]
        return sum(1 for x in valid if x.get("correct")) / max(1, len(valid)) if valid else None

    analysis = {}
    if "B" in conf and "A" in conf:
        analysis["A_vs_B"] = paired(conf["B"], conf["A"])
    if "B" in conf and "O" in conf:
        analysis["O_vs_B"] = paired(conf["B"], conf["O"])
    if "A" in conf and "O" in conf:
        analysis["A_vs_O"] = paired(conf["O"], conf["A"])
    pvals = {k: v["mcnemar_exact_p_two_sided"] for k, v in analysis.items() if v.get("status") == "COMPLETE"}
    holm = holm_adjust(pvals) if pvals else {}

    summary = {
        "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
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
        "experiment_complete": budget.stop is None,
        "incomplete_reason": budget.stop,
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
