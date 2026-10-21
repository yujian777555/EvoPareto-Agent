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
        self.cost += float(row.get("cost_usd") or 0)
        self.tok_in += int(row.get("tokens_in") or 0)
        self.tok_out += int(row.get("tokens_out") or 0)

    def dump(self):
        return {
            "evidence_class": "R35_LEDGER",
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


def to_task(t):
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


def fails_from(prog, tasks, rows):
    out = []
    for t, r in zip(tasks, rows):
        out.append(FailureRecord(
            task_id=t.task_id, parent_program_id=prog.program_id,
            parent_graph_sha256=hash_program(prog), success=bool(r.get("correct")),
            error_category="ANSWER_MISMATCH" if not r.get("correct") else "NO_FAILURE",
            predicted=r.get("predicted"), gold=t.gold_answer, diagnosis_uses_gold=True,
        ))
    return out


def paired(a_rows, b_rows):
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
            "mcnemar_exact_p_two_sided": p, "n": len(a_rows)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="limit to 2 dev + 2 confirm offline smoke")
    ap.add_argument("--out", default=str(TS / "live_r35"))
    args = ap.parse_args()
    if not args.mock and not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2
    if not args.mock:
        print("BLOCKED: real execution requires explicit new authorization (R3.5.1)")
        return 3

    ts = json.loads((TS / "taskset_r35.json").read_text(encoding="utf-8"))
    man = json.loads((TS / "taskset_r35_manifest.json").read_text(encoding="utf-8"))
    dev_tasks = [to_task(t) for t in ts["dev"]["tasks"]]
    conf_tasks = [to_task(t) for t in ts["confirm"]["tasks"]]
    if args.smoke:
        dev_tasks = dev_tasks[:2]
        conf_tasks = conf_tasks[:2]

    parent = load_frozen_parent(FROZEN)
    budget = Budget()
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    # Dev P
    p_dev = run_arm(parent, dev_tasks, budget, "dev:P", args.mock)
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

    def acc(rows):
        return sum(1 for x in rows if x.get("correct")) / max(1, len(rows))

    scores = {k: acc(v) for k, v in dev_rows.items() if k != "P" and v}
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

    # Confirm — all arms with a program
    arms = {}
    for name, prog in (("P", parent), ("R", child_r), ("F_old", f_old), ("F_local", f_local), ("E2_local", e2)):
        if prog:
            arms[name] = prog
    conf = {n: run_arm(p, conf_tasks, budget, f"conf:{n}", args.mock) for n, p in arms.items()}

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

    summary = {
        "evidence_class": "SIMULATED" if args.mock else "REAL_MODEL",
        "protocol": "MICRO-R3.5.1",
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
        "confirm_accuracy": {k: acc(v) for k, v in conf.items()},
        "paired_analysis": analysis,
        "requests_total": budget.n,
        "cost_usd_total": round(budget.cost, 8),
        "stop_reason": budget.stop,
        "budget": {"max_physical": MAX_PHYSICAL, "max_cost_usd": MAX_COST_USD},
        "confirm_used_for_selection": False,
        "statistical_claim": "EXPLORATORY_ONLY" if not args.mock else "SIMULATED_ONLY",
    }
    lineage = {
        "P": {"program_id": parent.program_id, "graph_sha256": hash_program(parent), "generation": 0},
        "R": rec_r, "F_old": rec_f_old, "F_local": rec_f_local, "E2_local": rec_e2,
        "winner": {"arm": winner_name, "program_id": winner.program_id if winner else None},
    }
    (outdir / "protocol.json").write_text(json.dumps({**man, "model": MODEL_ID, "arms": list(arms)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "candidate_lineage.json").write_text(json.dumps(lineage, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (outdir / "failure_archive.json").write_text(json.dumps({
        "parent_dev": [f.to_dict() for f in p_fails],
        "winner_dev": [f.to_dict() for f in winner_fails],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_results.json").write_text(json.dumps({"dev": dev_rows, "confirm": conf}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "paired_analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "request_ledger.json").write_text(json.dumps(budget.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "REPORT.md").write_text(
        f"# MICRO-R3.5.1\n\nMode: **{'SIMULATED' if args.mock else 'REAL'}**\n\n"
        f"- requests={budget.n} cost=${budget.cost:.6f}\n- winner={winner_name} scores={scores}\n"
        f"- E2: {summary['e2_status']} from={summary['e2_feedback_from']} src={summary['e2_source_task_ids']}\n"
        f"- confirm={summary['confirm_accuracy']}\n\n**Not RSI proof.**\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
