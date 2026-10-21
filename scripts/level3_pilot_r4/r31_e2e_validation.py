"""R3.2 offline E2E — fixed Mock fixtures + E2 feedback from gen-1 winner.

SIMULATED_DOCKER_IPC. Zero real API.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List

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
from src.research.r4_workflow_program import load_frozen_parent, program_provenance

OUT = ROOT / "results" / "level3_pilot_r4_micro_r32_offline"
TRAIN = ROOT / "results" / "level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
SEED = 20260603
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"

SCREENING = [5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752]
DEV = [4336, 2201, 2495, 5648, 4346]
CONFIRM = [3098, 6031, 4459, 6404, 2184, 1856, 856, 4627]
PRIOR_USED = set(range(0, 8)) | {6245, 499, 6996, 4900, 2518, 3741, 475, 5516, 2354, 1139, 1066, 3324, 7193}

# Pre-fixed task-level fixtures (NOT derived from gold at runtime).
# SIMULATED evidence only. Keys are task_ids.
FIXTURE_WRONG = "Step by step. Answer: -999"
FIXTURE_OK = "Compute. Answer: 12345"

# Parent dev: force failure on first DEV task only (pre-declared).
PARENT_DEV_FIXTURE = {
    f"gsm8k-train-{DEV[0]:04d}": FIXTURE_WRONG,
}


class TaskFixtureMailbox:
    """Explicit per-call fixture mailbox.

    Responses are bound to the *task* at construction time (one mailbox per
    task-run). Prompts do not need to contain the task id. Unconfigured calls
    raise — no silent default fallback.
    """

    def __init__(self, response: str, *, evidence: str = "SIMULATED"):
        if not response:
            raise ValueError("FIXTURE_RESPONSE_EMPTY")
        self.response = response
        self.evidence = evidence
        self.calls: List[str] = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        return self.response

    def get_usage_summary(self):
        return {"total_cost": 0.0}


class UnconfiguredMailbox(TaskFixtureMailbox):
    def __init__(self):
        super().__init__("UNCONFIGURED")
        self.response = ""

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        raise RuntimeError("FIXTURE_NOT_CONFIGURED")


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


def to_task(i: int, row) -> GSM8KTask:
    return GSM8KTask(f"gsm8k-train-{i:04d}", row["question"], row["gold"], row["answer_raw"], "train")


def fixture_for(tid: str, extra: Dict[str, str]) -> str:
    """Deterministic fixture lookup. Raises if unconfigured."""
    if tid in extra:
        return extra[tid]
    return FIXTURE_OK


def run_arm(prog, tasks, extra_fixtures: Dict[str, str]) -> List[Dict[str, Any]]:
    rows = []
    for t in tasks:
        resp = fixture_for(t.task_id, extra_fixtures)
        box = TaskFixtureMailbox(resp)
        r = execute_candidate_docker(prog, t.question, llm=box, task_id=t.task_id, expect_graph_sha256=hash_program(prog))
        sc = evaluate_workflow_output(t, r.get("answer_text") or "")
        rows.append({
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
            "fixture": resp,
            "production_entry": r.get("production_entry"),
        })
    return rows


def records_from_dev(prog, dev_tasks, dev_rows) -> List[FailureRecord]:
    out = []
    for t, row in zip(dev_tasks, dev_rows):
        out.append(FailureRecord(
            task_id=t.task_id,
            parent_program_id=prog.program_id,
            parent_graph_sha256=hash_program(prog),
            success=bool(row.get("correct")),
            error_category="ANSWER_MISMATCH" if not row.get("correct") else "NO_FAILURE",
            predicted=row.get("predicted"),
            gold=t.gold_answer,
            diagnosis_uses_gold=True,
            diagnostic="host-side scoring only; gold not in solve prompt",
        ))
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    assert hashlib.sha256(TRAIN.read_bytes()).hexdigest() == TRAIN_SHA
    rows = load_rows()
    all_new = set(SCREENING) | set(DEV) | set(CONFIRM)
    assert len(all_new) == 23 and not (all_new & PRIOR_USED)

    parent = load_frozen_parent(FROZEN)
    parent_sha = hash_program(parent)
    dev_tasks = [to_task(i, rows[i]) for i in DEV]
    confirm_tasks = [to_task(i, rows[i]) for i in CONFIRM]

    # --- Parent dev (feedback source for later comparison only) ---
    parent_dev = run_arm(parent, dev_tasks, PARENT_DEV_FIXTURE)
    assert any(not r["correct"] for r in parent_dev), "fixture must produce a Parent dev failure"

    # --- Gen1: R and F ---
    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
    assert child_r is not None
    # F needs feedback: use Parent dev FailureRecords (this is legitimate for
    # choosing F's operator from Parent failures; E2 must use winner's records)
    parent_summary = summarize_feedback(records_from_dev(parent, dev_tasks, parent_dev))
    child_f, rec_f = build_feedback_child(parent, parent_summary, seed=SEED, slot=2)

    r_rows = run_arm(child_r, dev_tasks, {})
    f_rows = run_arm(child_f, dev_tasks, {}) if child_f else []
    r_acc = sum(1 for x in r_rows if x["correct"]) / max(1, len(r_rows))
    f_acc = (sum(1 for x in f_rows if x["correct"]) / len(f_rows)) if f_rows else 0.0
    scores = {"R": r_acc, "F": f_acc}
    order = ["R", "F"]
    winner_name = max(order, key=lambda n: (scores[n], -order.index(n)))
    winner = child_r if winner_name == "R" else child_f
    winner_rows = r_rows if winner_name == "R" else f_rows

    # --- E2 feedback MUST come from gen-1 winner's own dev records ---
    winner_records = records_from_dev(winner, dev_tasks, winner_rows)
    winner_summary = summarize_feedback(winner_records)
    e2, rec_e2 = build_feedback_child(winner, winner_summary, seed=SEED, slot=3)
    e2_rows = run_arm(e2, dev_tasks, {}) if e2 else []

    # Confirm paired (fixtures independent of selection)
    def conf_fixtures():
        return {}

    p_conf = run_arm(parent, confirm_tasks, conf_fixtures())
    w_conf = run_arm(winner, confirm_tasks, conf_fixtures())
    e_conf = run_arm(e2, confirm_tasks, conf_fixtures()) if e2 else []

    # Unconfigured mailbox must fail loudly
    try:
        UnconfiguredMailbox()._request("x")
        unconf_ok = False
    except RuntimeError:
        unconf_ok = True

    child_r2, _ = apply_random_mutation(parent, seed=SEED, slot=1)
    report = {
        "evidence_class": "SIMULATED_DOCKER_IPC_E2E",
        "seed": SEED,
        "fixture_policy": {
            "type": "task-level explicit fixtures",
            "gold_used_to_build_fixtures": False,
            "silent_default_fallback": False,
            "unconfigured_raises": unconf_ok,
            "parent_dev_forced_failure_task": f"gsm8k-train-{DEV[0]:04d}",
        },
        "splits": {"screening": SCREENING, "dev": DEV, "confirm": CONFIRM, "disjoint": True},
        "parent_sha": parent_sha,
        "parent_dev_rows": parent_dev,
        "parent_dev_summary": parent_summary.to_dict(),
        "dev_scores": scores,
        "gen1_winner": winner_name,
        "winner_dev_rows": winner_rows,
        "winner_feedback": winner_summary.to_dict(),
        "e2_feedback_from_winner": rec_e2.get("feedback_label") or rec_e2.get("reason"),
        "e2_parent_ok": rec_e2.get("parent_program_id") == winner.program_id,
        "e2_generation": e2.generation if e2 else None,
        "e2_status": rec_e2.get("status"),
        "exec_flags": {
            "P": all(r["executed_graph_source"] for r in p_conf),
            "R": all(r["executed_graph_source"] for r in r_rows),
            "F": all(r["executed_graph_source"] for r in f_rows) if f_rows else False,
            "E2": all(r["executed_graph_source"] for r in e_conf) if e_conf else False,
        },
        "reproducible_mutations": hash_program(child_r) == hash_program(child_r2),
        "confirm_rows": {"P": p_conf, "winner": w_conf, "E2": e_conf},
        "confirm_used_for_selection": False,
        "statistical_claim": "NONE — SIMULATED fixtures",
    }
    (OUT / "r32_e2e_validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("dev_scores", "gen1_winner", "e2_parent_ok", "e2_generation", "e2_feedback_from_winner", "exec_flags", "reproducible_mutations")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
