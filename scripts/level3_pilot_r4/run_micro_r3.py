"""R3 real-model experiment entry (Docker/IPC). Default is MOCK rehearsal.

Real mode requires DEEPSEEK_API_KEY and is NOT authorized in R3.2 — only
--mock runs are permitted this round (0 real HTTP, $0).

Every real request would go through independent R3 ledger with pre-send
remaining budget checks (reserve worst-case before send).
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
MAX_PHYSICAL = 55
MAX_COST_USD = 0.05
MAX_IN, MAX_OUT = 1500, 300
SEED = 20260603
TRAIN = ROOT / "results/level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
OUT = ROOT / "results" / "level3_pilot_r4_micro_r3_run"

DEV = [4336, 2201, 2495, 5648, 4346]
CONFIRM = [3098, 6031, 4459, 6404, 2184, 1856, 856, 4627]

FIXTURE_OK = "Compute. Answer: 12345"
FIXTURE_WRONG = "Step by step. Answer: -999"


class R3Ledger:
    def __init__(self, path: Path):
        self.path = path
        self.rows: List[Dict[str, Any]] = []
        self.n = 0
        self.cost = 0.0
        self.tok_in = 0
        self.tok_out = 0
        self.stop: Optional[str] = None

    def precheck(self, est_in: int) -> str:
        if self.stop:
            return self.stop
        if self.n >= MAX_PHYSICAL:
            self.stop = "REQUEST_CAP_REACHED"
            return self.stop
        # reserve worst-case cost BEFORE send (not only after cap)
        reserve = worst_case_cost(MODEL_ID, min(est_in, MAX_IN), MAX_OUT)
        if self.cost + reserve > MAX_COST_USD:
            self.stop = "COST_RESERVE_EXCEEDED"
            return self.stop
        return ""

    def add(self, row: Dict[str, Any]) -> None:
        self.rows.append(row)
        self.n += 1
        self.cost += float(row.get("cost_usd") or 0.0)
        self.tok_in += int(row.get("tokens_in") or 0)
        self.tok_out += int(row.get("tokens_out") or 0)

    def dump(self):
        return {
            "evidence_class": "REAL_OR_MOCK_R3_LEDGER",
            "model": MODEL_ID,
            "n_physical_requests": self.n,
            "total_cost_usd": round(self.cost, 8),
            "tokens_in": self.tok_in,
            "tokens_out": self.tok_out,
            "stop_reason": self.stop,
            "max_physical": MAX_PHYSICAL,
            "max_cost_usd": MAX_COST_USD,
            "requests": self.rows,
        }


def real_chat(prompt: str, ledger: R3Ledger, *, task_id: str, phase: str) -> Dict[str, Any]:
    est = conservative_input_tokens(prompt)
    err = ledger.precheck(est)
    if err:
        return {"ok": False, "error": err, "content": "", "skipped": True}
    body = json.dumps({
        "model": MODEL_ID,
        "thinking": {"type": "disabled"},
        "max_tokens": MAX_OUT,
        "messages": [{"role": "user", "content": prompt[: MAX_IN * 3]}],
    }).encode("utf-8")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(
        f"{BASE_URL}/chat/completions",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
    )
    row = {"phase": phase, "task_id": task_id, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "estimated_input_tokens": est}
    t0 = time.time()
    try:
        with opener.open(req, timeout=90) as resp:
            raw = resp.read()
            status = int(resp.status)
        row["http_status"] = status
        row["latency_s"] = round(time.time() - t0, 3)
    except Exception as e:
        row.update({"error": f"{type(e).__name__}:{e}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
        ledger.add(row)
        return {"ok": False, "error": row["error"], "content": ""}
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as e:
        row.update({"error": f"JSON:{type(e).__name__}", "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "settle": "fail_closed_unknown"})
        ledger.add(row)
        return {"ok": False, "error": row["error"], "content": ""}
    usage = data.get("usage") or {}
    t_in = int(usage.get("prompt_tokens") or 0)
    t_out = int(usage.get("completion_tokens") or 0)
    content = ""
    choices = data.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content") or ""
    cost = estimate_cost(MODEL_ID, t_in, t_out, peak=True)
    row.update({"tokens_in": t_in, "tokens_out": t_out, "cost_usd": cost, "settle": "settled_actual", "usage_raw": usage})
    ledger.add(row)
    return {"ok": status == 200, "content": content, "cost_usd": cost}


class RealIPCMailbox:
    """Host-side mailbox bridging Docker IPC to real_chat / mock fixture."""

    def __init__(self, ledger: R3Ledger, task_id: str, phase: str, mock_response: Optional[str] = None, mock_mode: bool = False):
        self.ledger = ledger
        self.task_id = task_id
        self.phase = phase
        self.mock_response = mock_response
        self.mock_mode = mock_mode
        self.calls: List[str] = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        if self.mock_mode:
            if self.mock_response is None:
                raise RuntimeError("FIXTURE_NOT_CONFIGURED")
            # mock does not debit real ledger
            return self.mock_response
        r = real_chat(str(prompt), self.ledger, task_id=self.task_id, phase=self.phase)
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "MODEL_FAIL")
        return r.get("content") or ""

    def get_usage_summary(self):
        return {"total_cost": 0.0}


def load_rows():
    rows = {}
    with TRAIN.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            ans = o["answer"]
            gold = ans.rsplit("####", 1)[-1].strip() if "####" in ans else ans.strip()
            rows[i] = {"index": i, "question": o["question"], "answer_raw": ans, "gold": " ".join(gold.split())}
    return rows


def to_task(i, row):
    return GSM8KTask(f"gsm8k-train-{i:04d}", row["question"], row["gold"], row["answer_raw"], "train")


def run_arm(prog, tasks, *, ledger, phase, mock_mode, extra_fixtures=None):
    extra_fixtures = extra_fixtures or {}
    out = []
    for t in tasks:
        mock_resp = extra_fixtures.get(t.task_id, FIXTURE_OK if mock_mode else None)
        box = RealIPCMailbox(ledger, t.task_id, phase, mock_response=mock_resp, mock_mode=mock_mode)
        try:
            r = execute_candidate_docker(prog, t.question, llm=box, task_id=t.task_id, expect_graph_sha256=hash_program(prog))
        except Exception as e:
            r = {"ok": False, "error": f"{type(e).__name__}:{e}", "answer_text": None, "executed_graph_source": False}
        sc = evaluate_workflow_output(t, r.get("answer_text") or "")
        out.append({
            "task_id": t.task_id,
            "program_id": r.get("program_id"),
            "graph_sha256": r.get("graph_sha256"),
            "graph_sha256_match": r.get("graph_sha256_match"),
            "executed_graph_source": r.get("executed_graph_source"),
            "ok": r.get("ok"),
            "n_llm_calls": r.get("n_llm_calls"),
            "predicted": sc.get("predicted"),
            "correct": bool(sc.get("correct")),
            "error": r.get("error"),
            "phase": phase,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="SIMULATED rehearsal only (no real API)")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    mock_mode = bool(args.mock)
    if not mock_mode and not os.environ.get("DEEPSEEK_API_KEY"):
        print("BLOCKED: DEEPSEEK_API_KEY missing")
        return 2
    if not mock_mode:
        print("NOTE: real mode is NOT authorized in R3.2 — use --mock")
        return 3

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    parent = load_frozen_parent(FROZEN)
    dev_tasks = [to_task(i, rows[i]) for i in DEV]
    conf_tasks = [to_task(i, rows[i]) for i in CONFIRM]
    ledger = R3Ledger(outdir / "request_ledger.json")

    # Parent dev: one forced failure fixture (feedback source)
    parent_dev_fix = {dev_tasks[0].task_id: FIXTURE_WRONG}
    parent_dev = run_arm(parent, dev_tasks, ledger=ledger, phase="dev:P", mock_mode=mock_mode, extra_fixtures=parent_dev_fix)
    assert any(not r["correct"] for r in parent_dev)

    parent_records = []
    for t, row in zip(dev_tasks, parent_dev):
        parent_records.append(FailureRecord(
            task_id=t.task_id,
            parent_program_id=parent.program_id,
            parent_graph_sha256=hash_program(parent),
            success=bool(row.get("correct")),
            error_category="ANSWER_MISMATCH" if not row.get("correct") else "NO_FAILURE",
            predicted=row.get("predicted"),
            gold=t.gold_answer,
            diagnosis_uses_gold=True,
        ))
    parent_summary = summarize_feedback(parent_records)

    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
    child_f, rec_f = build_feedback_child(parent, parent_summary, seed=SEED, slot=2)

    r_rows = run_arm(child_r, dev_tasks, ledger=ledger, phase="dev:R", mock_mode=mock_mode)
    f_rows = run_arm(child_f, dev_tasks, ledger=ledger, phase="dev:F", mock_mode=mock_mode) if child_f else []
    scores = {
        "R": sum(1 for x in r_rows if x["correct"]) / max(1, len(r_rows)),
        "F": (sum(1 for x in f_rows if x["correct"]) / len(f_rows)) if f_rows else 0.0,
    }
    winner_name = max(["R", "F"], key=lambda n: (scores[n], -["R", "F"].index(n)))
    winner = child_r if winner_name == "R" else child_f
    winner_rows = r_rows if winner_name == "R" else f_rows

    winner_records = [
        FailureRecord(
            task_id=t.task_id,
            parent_program_id=winner.program_id,
            parent_graph_sha256=hash_program(winner),
            success=bool(row.get("correct")),
            error_category="ANSWER_MISMATCH" if not row.get("correct") else "NO_FAILURE",
            predicted=row.get("predicted"),
            gold=t.gold_answer,
            diagnosis_uses_gold=True,
        )
        for t, row in zip(dev_tasks, winner_rows)
    ]
    winner_summary = summarize_feedback(winner_records)
    e2, rec_e2 = build_feedback_child(winner, winner_summary, seed=SEED, slot=3)
    e2_rows = run_arm(e2, dev_tasks, ledger=ledger, phase="dev:E2", mock_mode=mock_mode) if e2 else []

    p_conf = run_arm(parent, conf_tasks, ledger=ledger, phase="conf:P", mock_mode=mock_mode)
    w_conf = run_arm(winner, conf_tasks, ledger=ledger, phase="conf:winner", mock_mode=mock_mode)
    e_conf = run_arm(e2, conf_tasks, ledger=ledger, phase="conf:E2", mock_mode=mock_mode) if e2 else []

    summary = {
        "evidence_class": "SIMULATED_REHEARSAL" if mock_mode else "REAL_MODEL",
        "mock_mode": mock_mode,
        "dev_scores": scores,
        "gen1_winner": winner_name,
        "e2_parent_ok": rec_e2.get("parent_program_id") == winner.program_id,
        "e2_generation": e2.generation if e2 else None,
        "e2_status": rec_e2.get("status"),
        "e2_feedback_label": rec_e2.get("feedback_label") or rec_e2.get("reason"),
        "requests_total": ledger.n,
        "cost_usd_total": round(ledger.cost, 8),
        "budget_baseline_requests": 50,
        "budget_suggested_cap_requests": MAX_PHYSICAL,
        "budget_cap_usd": MAX_COST_USD,
        "confirm_used_for_selection": False,
        "statistical_claim": "NONE" if mock_mode else "PENDING_ANALYSIS",
    }
    (outdir / "protocol.json").write_text(json.dumps({
        "evidence_class": summary["evidence_class"],
        "seed": SEED,
        "model": MODEL_ID,
        "dev": DEV,
        "confirm": CONFIRM,
        "budget": {"baseline": 50, "suggested_cap": MAX_PHYSICAL, "max_cost_usd": MAX_COST_USD},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "candidate_lineage.json").write_text(json.dumps({
        "P": {"program_id": parent.program_id, "graph_sha256": hash_program(parent), "generation": 0},
        "R": rec_r,
        "F": rec_f,
        "E2": rec_e2,
    }, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    (outdir / "paired_results.json").write_text(json.dumps({
        "dev": {"P": parent_dev, "R": r_rows, "F": f_rows, "E2": e2_rows},
        "confirm": {"P": p_conf, "winner": w_conf, "E2": e_conf},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "request_ledger.json").write_text(json.dumps(ledger.dump(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (outdir / "REPORT.md").write_text(
        f"# MICRO-R3 run report\n\nMode: **{'SIMULATED mock rehearsal' if mock_mode else 'REAL'}**\n\n"
        f"- requests={ledger.n} cost=${ledger.cost:.6f}\n- winner={winner_name} scores={scores}\n"
        f"- e2_parent_ok={summary['e2_parent_ok']} gen={summary['e2_generation']}\n\n"
        "**Not real-model performance if mock_mode.**\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
