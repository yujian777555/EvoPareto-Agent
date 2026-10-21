"""MICRO-R3.4-HARDSET real experiment entry (Docker/IPC + DeepSeek).

Independent experiment ledger. Pre-send budget reserve. --mock for rehearsal.
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
from src.research.r4_workflow_program import load_frozen_parent
from src.runtime.provider_gateway import conservative_input_tokens, estimate_cost, worst_case_cost

MODEL_ID = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"
MAX_PHYSICAL = 165
MAX_COST_USD = 0.15
MAX_IN, MAX_OUT = 1500, 300
SEED = 20260604
FROZEN = ROOT / "results/level3_pilot_r2" / "frozen_candidates"
TS = ROOT / "results/level3_pilot_r4_micro_r34"


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
        self.cost += float(row.get("cost_usd") or 0)
        self.tok_in += int(row.get("tokens_in") or 0)
        self.tok_out += int(row.get("tokens_out") or 0)

    def dump(self):
        return {
            "evidence_class": "R34_LEDGER",
            "n_physical_requests": self.n,
            "total_cost_usd": round(self.cost, 8),
            "tokens_in": self.tok_in,
            "tokens_out": self.tok_out,
            "stop_reason": self.stop,
            "max_physical": MAX_PHYSICAL,
            "max_cost_usd": MAX_COST_USD,
            "requests": self.rows,
        }


class Mailbox:
    def __init__(self, budget: Budget, task_id: str, phase: str, mock: Optional[str], mock_mode: bool):
        self.budget, self.task_id, self.phase = budget, task_id, phase
        self.mock, self.mock_mode = mock, mock_mode
        self.calls: List[str] = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
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
        data = json.loads(raw.decode("utf-8"))
        usage = data.get("usage") or {}
        t_in, t_out = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        content = ""
        ch = data.get("choices") or []
        if ch:
            content = (ch[0].get("message") or {}).get("content") or ""
        cost = estimate_cost(MODEL_ID, t_in, t_out, peak=True)
        row.update({"tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost, "settle": "settled_actual", "usage_raw": usage})
        self.budget.add(row)
        return content

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def to_task(t: Dict[str, Any]) -> GSM8KTask:
    return GSM8KTask(t["task_id"], t["question"], t["gold_answer"], f"#### {t['gold_answer']}", "train")


def run_arm(prog, tasks, budget, phase, mock_mode, fixtures=None):
    fixtures = fixtures or {}
    rows = []
    for t in tasks:
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
    imp = reg = both_c = both_w = 0
    for a, b in zip(a_rows, b_rows):
        if b["correct"] and not a["correct"]:
            imp += 1
        elif a["correct"] and not b["correct"]:
            reg += 1
        elif a["correct"] and b["correct"]:
            both_c += 1
        else:
            both_w += 1
    # exact mcnemar two-sided
    n = imp + reg
    if n == 0:
        p = 1.0
    else:
        from math import comb
        k = min(imp, reg)
        p = min(1.0, 2 * sum(comb(n, i) for i in range(0, k + 1)) / (2 ** n))
    return {"improved": imp, "regressed": reg, "both_correct": both_c, "both_wrong": both_w,
            "mcnemar_exact_p_two_sided": p, "n": len(a_rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--out", default=str(TS / "live"))
    args = ap.parse_args()
    if not args.mock and not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2

    ts = json.loads((TS / "taskset.json").read_text(encoding="utf-8"))
    man = json.loads((TS / "taskset_manifest.json").read_text(encoding="utf-8"))
    calib_tasks = [to_task(t) for t in ts["calibration"]["tasks"]]
    dev_tasks = [to_task(t) for t in ts["dev"]["tasks"]]
    conf_tasks = [to_task(t) for t in ts["confirm"]["tasks"]]

    parent = load_frozen_parent(FROZEN)
    budget = Budget()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # Calibration: Parent
    calib_rows = run_arm(parent, calib_tasks, budget, "calib:P", args.mock)
    calib_fails = [FailureRecord(
        task_id=r["task_id"], parent_program_id=parent.program_id,
        parent_graph_sha256=hash_program(parent), success=bool(r["correct"]),
        error_category="ANSWER_MISMATCH" if not r["correct"] else "NO_FAILURE",
        predicted=r.get("predicted"), gold=t.gold_answer, diagnosis_uses_gold=True,
        diagnostic="host-side only",
    ) for r, t in zip(calib_rows, calib_tasks)]

    # Also run Parent on dev (feedback source for F / fair baseline)
    p_dev = run_arm(parent, dev_tasks, budget, "dev:P", args.mock)
    p_dev_fails = [FailureRecord(
        task_id=r["task_id"], parent_program_id=parent.program_id,
        parent_graph_sha256=hash_program(parent), success=bool(r["correct"]),
        error_category="ANSWER_MISMATCH" if not r["correct"] else "NO_FAILURE",
        predicted=r.get("predicted"), gold=t.gold_answer, diagnosis_uses_gold=True,
    ) for r, t in zip(p_dev, dev_tasks)]
    parent_feedback = summarize_feedback(p_dev_fails + calib_fails)

    # Gen1 R and F
    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
    child_f, rec_f = build_feedback_child(parent, parent_feedback, seed=SEED, slot=2)
    r_rows = run_arm(child_r, dev_tasks, budget, "dev:R", args.mock) if child_r else []
    f_rows = run_arm(child_f, dev_tasks, budget, "dev:F", args.mock) if child_f else []

    def acc(rows):
        return sum(1 for x in rows if x.get("correct")) / max(1, len(rows))

    scores = {}
    if child_r:
        scores["R"] = acc(r_rows)
    if child_f:
        scores["F"] = acc(f_rows)
    order = [k for k in ("R", "F") if k in scores]
    winner_name = max(order, key=lambda n: (scores[n], -order.index(n))) if order else None
    winner = {"R": child_r, "F": child_f}.get(winner_name)
    winner_rows = {"R": r_rows, "F": f_rows}.get(winner_name, [])
    winner_fails = [FailureRecord(
        task_id=r["task_id"], parent_program_id=winner.program_id,
        parent_graph_sha256=hash_program(winner), success=bool(r["correct"]),
        error_category="ANSWER_MISMATCH" if not r["correct"] else "NO_FAILURE",
        predicted=r.get("predicted"), gold=t.gold_answer, diagnosis_uses_gold=True,
    ) for r, t in zip(winner_rows, dev_tasks)] if winner else []
    winner_fb = summarize_feedback(winner_fails)
    e2, rec_e2 = (build_feedback_child(winner, winner_fb, seed=SEED, slot=3) if winner else (None, {"status": "NOT_GENERATED_NO_FAILURE", "reason": "NO_WINNER"}))
    e2_rows = run_arm(e2, dev_tasks, budget, "dev:E2", args.mock) if e2 else []

    # Confirm paired — all available arms
    arms = {"P": parent}
    if child_r:
        arms["R"] = child_r
    if child_f:
        arms["F"] = child_f
    if e2:
        arms["E2"] = e2
    conf = {name: run_arm(prog, conf_tasks, budget, f"conf:{name}", args.mock) for name, prog in arms.items()}

    analysis = {}
    base = conf["P"]
    for name in conf:
        if name == "P":
            continue
        analysis[f"P_vs_{name}"] = paired(base, conf[name])
    if "R" in conf and "F" in conf:
        analysis["F_vs_R"] = paired(conf["R"], conf["F"])
    if e2 and winner_name:
        analysis[f"E2_vs_{winner_name}"] = paired(conf.get(winner_name, []), conf.get("E2", []))

    summary = {
        "evidence_class": "REAL_MODEL" if not args.mock else "SIMULATED",
        "protocol": "MICRO-R3.4-HARDSET",
        "seed": SEED,
        "taskset_sha256": {"calib": man["calibration_task_set_sha256"], "confirm": man["confirm_task_set_sha256"], "dev": man["dev_task_set_sha256"]},
        "n_calib": len(calib_tasks), "n_dev": len(dev_tasks), "n_confirm": len(conf_tasks),
        "parent_calib_accuracy": acc(calib_rows),
        "parent_calib_errors": sum(1 for r in calib_rows if not r["correct"]),
        "parent_dev_accuracy": acc(p_dev),
        "dev_scores": scores,
        "gen1_winner": winner_name,
        "f_status": rec_f.get("status"), "f_feedback": rec_f.get("feedback_label") or rec_f.get("reason"),
        "e2_status": rec_e2.get("status"), "e2_reason": rec_e2.get("reason"), "e2_generation": e2.generation if e2 else None,
        "e2_parent_ok": (rec_e2.get("parent_program_id") == winner.program_id) if winner and e2 else False,
        "confirm_accuracy": {k: acc(v) for k, v in conf.items()},
        "paired_analysis": analysis,
        "feedback_utilization": {
            "parent_failures": sum(1 for r in calib_fails + p_dev_fails if not r.success),
            "f_generated": child_f is not None,
            "e2_generated": e2 is not None,
        },
        "requests_total": budget.n,
        "cost_usd_total": round(budget.cost, 8),
        "tokens_in": budget.tok_in, "tokens_out": budget.tok_out,
        "stop_reason": budget.stop,
        "budget": {"max_physical": MAX_PHYSICAL, "max_cost_usd": MAX_COST_USD},
        "statistical_claim": "EXPLORATORY_ONLY_NOT_CONFIRMATORY",
    }

    lineage = {"P": {"program_id": parent.program_id, "graph_sha256": hash_program(parent), "generation": 0}}
    for name, rec, prog in (("R", rec_r, child_r), ("F", rec_f, child_f), ("E2", rec_e2, e2)):
        entry = dict(rec) if isinstance(rec, dict) else {}
        if prog:
            entry["graph_sha256"] = hash_program(prog)
            entry["generation"] = prog.generation
            entry["parent_program_id"] = prog.parent_program_id
        lineage[name] = entry

    (outdir / "protocol.json").write_text(json.dumps({**man, "model": MODEL_ID, "mode": "mock" if args.mock else "real"}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "candidate_lineage.json").write_text(json.dumps(lineage, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (outdir / "failure_archive.json").write_text(json.dumps({
        "evidence_class": "REAL_MODEL_FAILURES" if not args.mock else "SIMULATED",
        "calibration": [r.to_dict() for r in calib_fails],
        "dev_parent": [r.to_dict() for r in p_dev_fails],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_results.json").write_text(json.dumps({"calibration": calib_rows, "dev": {"P": p_dev, "R": r_rows, "F": f_rows, "E2": e2_rows}, "confirm": conf}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "request_ledger.json").write_text(json.dumps(budget.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "REPORT.md").write_text(
        f"# MICRO-R3.4-HARDSET\n\nMode: **{'SIMULATED' if args.mock else 'REAL'}**\n\n"
        f"- requests={budget.n} cost=${budget.cost:.6f} stop={budget.stop}\n"
        f"- Parent calib acc={summary['parent_calib_accuracy']:.2f} errors={summary['parent_calib_errors']}\n"
        f"- dev_scores={scores} winner={winner_name}\n"
        f"- F status={summary['f_status']} E2 status={summary['e2_status']} ({summary['e2_reason']})\n"
        f"- confirm acc={summary['confirm_accuracy']}\n- paired={json.dumps(analysis, sort_keys=True)}\n\n"
        "**Exploratory only. Not RSI proof.**\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
