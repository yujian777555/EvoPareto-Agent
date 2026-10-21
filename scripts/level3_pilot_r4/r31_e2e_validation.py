"""R3.1 offline end-to-end integration (SIMULATED Docker/IPC, zero real API).

Full flow: load Parent → R/F mutation → Parent dev feedback → select winner →
E2 from winner → dev selection → paired confirm interface → reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

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

OUT = ROOT / "results" / "level3_pilot_r4_micro_r31_offline"
TRAIN = ROOT / "results" / "level3_pilot_r4_data" / "gsm8k_train_official.jsonl"
TRAIN_SHA = "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"
SEED = 20260603
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"

# Frozen splits from R3 (TASKSET_AUDIT_AND_SPLIT.md)
SCREENING = [5895, 1540, 6485, 7068, 7166, 3011, 7396, 6596, 1900, 6752]
DEV = [4336, 2201, 2495, 5648, 4346]
CONFIRM = [3098, 6031, 4459, 6404, 2184, 1856, 856, 4627]
PRIOR_USED = set(range(0, 8)) | {6245, 499, 6996, 4900, 2518, 3741, 475, 5516, 2354, 1139, 1066, 3324, 7193}


class MockIPCMailbox:
    """Deterministic fake model for Docker IPC. Fixture-driven, not gold-driven."""

    def __init__(self, answers_by_task: Dict[str, str], default: str = "Reasoning. Answer: 42"):
        self.answers_by_task = answers_by_task
        self.default = default
        self.calls: List[str] = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        # respond based on task marker in prompt if present
        for tid, ans in self.answers_by_task.items():
            if tid in str(prompt):
                return ans
        return self.default

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


def to_task(i: int, row) -> GSM8KTask:
    return GSM8KTask(f"gsm8k-train-{i:04d}", row["question"], row["gold"], row["answer_raw"], "train")


def fixture_answers(rows, indices, *, force_fail_indices=()):
    """Pre-fixed mock outputs: correct-looking 'Answer: <gold-like>' but gold is
    used ONLY to shape mock strings in this offline fixture. Marked SIMULATED.
    For force_fail_indices the mock returns a deliberately wrong number."""
    out = {}
    for i in indices:
        tid = f"gsm8k-train-{i:04d}"
        if i in force_fail_indices:
            out[tid] = "Reasoning... Answer: -999"
        else:
            # neutral correct-ish token; scoring compares to gold separately
            out[tid] = "Reasoning... Answer: 12345"
    return out


def run_arm_on_tasks(prog, tasks, mailbox_factory: Callable[[str], Any]) -> List[Dict[str, Any]]:
    rows = []
    for t in tasks:
        box = mailbox_factory(t.task_id)
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
            "production_entry": r.get("production_entry"),
        })
    return rows


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    assert hashlib.sha256(TRAIN.read_bytes()).hexdigest() == TRAIN_SHA
    rows = load_rows()

    # split integrity
    all_new = set(SCREENING) | set(DEV) | set(CONFIRM)
    assert len(all_new) == 23
    assert not (all_new & PRIOR_USED)
    assert not set(SCREENING) & set(DEV)
    assert not set(DEV) & set(CONFIRM)
    assert not set(SCREENING) & set(CONFIRM)

    parent = load_frozen_parent(FROZEN)
    parent_sha = hash_program(parent)
    prov_parent = program_provenance(parent)

    # R / F from seeded random + feedback (feedback starts from Parent dev failures)
    child_r, rec_r = apply_random_mutation(parent, seed=SEED, slot=1)
    assert child_r is not None

    dev_tasks = [to_task(i, rows[i]) for i in DEV]
    confirm_tasks = [to_task(i, rows[i]) for i in CONFIRM]

    # Parent dev run (mock): force 1 failure for feedback generation
    parent_dev_rows = run_arm_on_tasks(
        parent,
        dev_tasks,
        lambda tid: MockIPCMailbox({tid: "Reasoning... Answer: -999"} if tid.endswith("4336") else {tid: "Reasoning... Answer: 1"}),
    )
    # Build FailureRecords from parent dev results (host-side gold compare only)
    fail_records = []
    for t, row in zip(dev_tasks, parent_dev_rows):
        ok = row["correct"]
        fail_records.append(FailureRecord(
            task_id=t.task_id,
            parent_program_id=parent.program_id,
            parent_graph_sha256=parent_sha,
            success=ok,
            error_category="ANSWER_MISMATCH" if not ok else "NO_FAILURE",
            predicted=row.get("predicted"),
            gold=t.gold_answer,
            diagnosis_uses_gold=True,
            diagnostic="host-side scoring only",
        ))
    summary = summarize_feedback(fail_records)
    child_f, rec_f = build_feedback_child(parent, summary, seed=SEED, slot=2)

    # Dev evaluation R vs F
    def box_for(tid):
        return MockIPCMailbox({tid: "Answer: 12345"})

    r_rows = run_arm_on_tasks(child_r, dev_tasks, box_for)
    f_rows = run_arm_on_tasks(child_f, dev_tasks, box_for) if child_f else []
    r_acc = sum(1 for x in r_rows if x["correct"]) / max(1, len(r_rows))
    f_acc = sum(1 for x in f_rows if x["correct"]) / max(1, len(f_rows)) if f_rows else 0.0
    order = ["R", "F"]
    scores = {"R": r_acc, "F": f_acc}
    winner_name = max(order, key=lambda n: (scores[n], -order.index(n)))
    winner = child_r if winner_name == "R" else child_f

    # E2 from winner using feedback summary of winner dev if available
    e2, rec_e2 = build_feedback_child(winner, summary, seed=SEED, slot=3)
    e2_rows = run_arm_on_tasks(e2, dev_tasks, box_for) if e2 else []

    # Confirm paired interface (same mock contract; no reverse selection)
    def box_confirm(tid):
        return MockIPCMailbox({tid: "Answer: 12345"})

    p_conf = run_arm_on_tasks(parent, confirm_tasks, box_confirm)
    w_conf = run_arm_on_tasks(winner, confirm_tasks, box_confirm)
    e_conf = run_arm_on_tasks(e2, confirm_tasks, box_confirm) if e2 else []

    # Reproducibility of mutations
    child_r2, _ = apply_random_mutation(parent, seed=SEED, slot=1)
    reproducible = hash_program(child_r) == hash_program(child_r2)

    lineage = [
        {"id": "P", "program_id": parent.program_id, "parent_program_id": None, "generation": 0, "graph_sha256": parent_sha, "status": "SUCCESS"},
        {"id": "R", **{k: rec_r.get(k) for k in ("operator", "params", "parent_program_id", "child_program_id", "child_graph_sha256", "generation", "status")}},
        {"id": "F", **{k: rec_f.get(k) for k in ("selected_operator", "operator", "parent_program_id", "child_program_id", "child_graph_sha256", "generation", "status", "feedback_label", "reason")}},
        {"id": "E2", **{k: rec_e2.get(k) for k in ("selected_operator", "parent_program_id", "child_program_id", "child_graph_sha256", "generation", "status", "reason")}},
    ]

    report = {
        "evidence_class": "SIMULATED_DOCKER_IPC_E2E",
        "seed": SEED,
        "train_sha256": TRAIN_SHA,
        "splits": {
            "screening": SCREENING, "dev": DEV, "confirm": CONFIRM,
            "disjoint": True, "excludes_prior": True, "n_prior_excluded": len(PRIOR_USED),
        },
        "parent": {"program_id": parent.program_id, "graph_sha256": parent_sha, "matches_frozen": prov_parent["graph_sha256"] == parent_sha},
        "dev_feedback_summary": summary.to_dict(),
        "dev_scores": scores,
        "gen1_winner": winner_name,
        "lineage": lineage,
        "exec_flags": {
            "P": all(r["executed_graph_source"] for r in p_conf),
            "R": all(r["executed_graph_source"] for r in r_rows),
            "F": all(r["executed_graph_source"] for r in f_rows) if f_rows else False,
            "E2": all(r["executed_graph_source"] for r in e_conf) if e_conf else False,
        },
        "graph_sha_match": {
            "P": all(r["graph_sha256_match"] for r in p_conf),
            "R": all(r["graph_sha256_match"] for r in r_rows),
            "E2": all(r["graph_sha256_match"] for r in e_conf) if e_conf else False,
        },
        "reproducible_mutations": reproducible,
        "dev_rows": {"P": parent_dev_rows, "R": r_rows, "F": f_rows, "E2": e2_rows},
        "confirm_rows": {"P": p_conf, winner_name: w_conf, "E2": e_conf},
        "budget_plan_note": "Parent dev 5 + R/F dev 10 + E2 dev 5 + confirm 24 + S probe 6 = 50; +10% -> 55",
        "statistical_claim": "NONE — SIMULATED fixtures; not real model performance",
    }
    (OUT / "r31_e2e_validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("dev_scores", "gen1_winner", "exec_flags", "graph_sha_match", "reproducible_mutations")}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
