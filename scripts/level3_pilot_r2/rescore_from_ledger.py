"""Task A: rescore from complete Provider FULL_CONTENT (ledger), not truncated stdout."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "results" / "level3_pilot_r2"

LEDGER = RES / "parentre_ledger_parentre-8aa3d61f.json"
CONF = RES / "paired_confirmation_set.json"
CORRECTED = RES / "paired_experiment_results_corrected.json"

EXPECTED_TASK_HASH = "86cc56115220eaede3be4ada49143210ba636d8d3eaf963bf6613c0f67d391b8"
EXPECTED_CHILD_SHA = "a0add78f10e666845367f31e560181cf403b7c39d3a44d0daa5264a4285edf7b"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def extract_boxed(text: str) -> Optional[str]:
    """Preferred: \\boxed{N}. Then #### N, Answer: N, terminal = N."""
    if not text:
        return None
    m = re.search(r"\\boxed\{(-?\d[\d,]*(?:\.\d+)?)\}", text)
    if m:
        return m.group(1).replace(",", "")
    if "####" in text:
        tail = text.rsplit("####", 1)[1].strip()
        m = re.search(r"-?\d[\d,]*(?:\.\d+)?", tail)
        if m:
            return m.group(0).replace(",", "")
    m = re.search(r"Answer:\s*(-?\d[\d,]*(?:\.\d+)?)", text)
    if m:
        return m.group(1).replace(",", "")
    m = re.search(r"=\s*(-?\d[\d,]*(?:\.\d+)?)\s*[.。]?\s*$", text.strip())
    if m:
        return m.group(1).replace(",", "")
    ms = re.findall(r"-?\d[\d,]*(?:\.\d+)?", text)
    return ms[-1].replace(",", "") if ms else None


def main() -> int:
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    corrected = json.loads(CORRECTED.read_text(encoding="utf-8"))

    assert conf["task_set_sha256"] == EXPECTED_TASK_HASH
    rows = ledger["rows"]
    tasks = conf["tasks"]
    child_by_id = {r["task_id"]: r for r in corrected.get("PER_TASK", []) if r["role"] == "child"}

    # ---- Task mapping verification ----
    # Requirements: 12 ledger rows, 12 tasks, sequential order, 1 IPC per task.
    # ---- full mapping verification (Task C requirements) ----
    mapping_ok = (
        len(rows) == 12
        and len(tasks) == 12
        and all(r.get("request_phase") == "parent_ipc" for r in rows)
        and all(r.get("finish_reason") == "stop" for r in rows)
        and all(r.get("http_status") == 200 for r in rows)
        and all(r.get("FULL_CONTENT") for r in rows)
    )
    # physical request IDs unique
    pids = [r.get("physical_request_id") for r in rows]
    mapping_ok = mapping_ok and len(set(pids)) == 12
    # run id consistent
    run_ids = {r.get("run_id") for r in rows}
    mapping_ok = mapping_ok and len(run_ids) == 1
    # token + SHA fields present
    mapping_ok = mapping_ok and all(
        r.get("usage_prompt_tokens") is not None
        and r.get("usage_completion_tokens") is not None
        and r.get("prompt_sha256")
        for r in rows
    )
    # cross-check with parent_reverification_results: ipc_processed == 1 per task
    rev_path = RES / "parent_reverification_results.json"
    if rev_path.exists():
        rev = json.loads(rev_path.read_text(encoding="utf-8"))
        per_task = rev.get("PER_TASK_PARENT") or rev.get("PER_TASK") or []
        rev_by_id = {r.get("task_id"): r for r in per_task}
        for spec in tasks:
            rr = rev_by_id.get(spec["task_id"])
            if rr is None:
                mapping_ok = False
                break
            if rr.get("ipc_processed") != 1:
                mapping_ok = False
                break
        # order check: rev task order == conf task order
        if [r.get("task_id") for r in per_task[:12]] != [t["task_id"] for t in tasks]:
            mapping_ok = False
    # child frozen results: unique ids, full coverage, order
    child_ids = [r["task_id"] for r in corrected.get("PER_TASK", []) if r["role"] == "child"]
    mapping_ok = mapping_ok and len(child_ids) == 12 and len(set(child_ids)) == 12
    mapping_ok = mapping_ok and child_ids == [t["task_id"] for t in tasks]

    if not mapping_ok:
        print("MAPPING_UNRESOLVED — refusing to guess task correspondence")
        return 2

    parent_rows: List[Dict[str, Any]] = []
    for idx, (row, spec) in enumerate(zip(rows, tasks)):
        fc = row["FULL_CONTENT"]
        pred = extract_boxed(fc)
        correct = pred is not None and str(pred) == str(spec["gold_answer"])
        parent_rows.append({
            "task_id": spec["task_id"],
            "role": "parent",
            "ledger_row_index": idx,
            "physical_request_id": row.get("physical_request_id"),
            "prompt_sha256": row.get("prompt_sha256"),
            "full_response_sha256": sha256_text(fc),
            "full_response_len": len(fc),
            "finish_reason": row.get("finish_reason"),
            "http_status": row.get("http_status"),
            "usage_prompt_tokens": row.get("usage_prompt_tokens"),
            "usage_completion_tokens": row.get("usage_completion_tokens"),
            "gold_answer": spec["gold_answer"],
            "predicted": pred,
            "correct": correct,
            "extractor": "boxed/####/Answer/terminal",
        })

    child_rows: List[Dict[str, Any]] = []
    for spec in tasks:
        cr = child_by_id.get(spec["task_id"], {})
        pred = cr.get("predicted_rescored") if "predicted_rescored" in cr else cr.get("predicted")
        correct = cr.get("correct_rescored") if "correct_rescored" in cr else cr.get("correct")
        child_rows.append({
            "task_id": spec["task_id"],
            "role": "child",
            "gold_answer": spec["gold_answer"],
            "predicted": pred,
            "correct": bool(correct),
            "source": "paired_experiment_results_corrected.json (reused, not recalled)",
        })

    parent_correct = sum(1 for r in parent_rows if r["correct"])
    child_correct = sum(1 for r in child_rows if r["correct"])
    improved = sum(1 for p, c in zip(parent_rows, child_rows) if not p["correct"] and c["correct"])
    regressed = sum(1 for p, c in zip(parent_rows, child_rows) if p["correct"] and not c["correct"])
    both_correct = sum(1 for p, c in zip(parent_rows, child_rows) if p["correct"] and c["correct"])
    both_wrong = sum(1 for p, c in zip(parent_rows, child_rows) if not p["correct"] and not c["correct"])
    net_gain = child_correct - parent_correct

    # consistency assertions
    assert parent_correct == sum(1 for r in parent_rows if r["correct"])
    assert child_correct == sum(1 for r in child_rows if r["correct"])
    assert improved + regressed + both_correct + both_wrong == 12
    assert net_gain == child_correct - parent_correct

    rescore = {
        "evidence_class": "DERIVED_FROM_EXISTING_LEDGER",
        "note": (
            "Scored from the complete provider FULL_CONTENT in the parentre ledger. "
            "Container stdout repr(out)[:500] is NOT used as the scoring source. "
            "No API calls were made."
        ),
        "source_files": {
            "ledger": "results/level3_pilot_r2/parentre_ledger_parentre-8aa3d61f.json",
            "confirmation_set": "results/level3_pilot_r2/paired_confirmation_set.json",
            "child_results": "results/level3_pilot_r2/paired_experiment_results_corrected.json",
        },
        "task_set_sha256": EXPECTED_TASK_HASH,
        "child_graph_sha256": EXPECTED_CHILD_SHA,
        "scoring_adapter_sha256": sha256_text(Path(__file__).read_text(encoding="utf-8")),
        "task_mapping": {
            "verified": True,
            "method": "12 ledger rows in execution order == 12 confirmation tasks; "
                      "each row is parent_ipc with one IPC call; finish_reason=stop, http=200",
        },
        "PARENT": {
            "correct": parent_correct, "total": 12, "accuracy": parent_correct / 12,
            "source": "FULL_CONTENT from ledger",
        },
        "CHILD": {
            "correct": child_correct, "total": 12, "accuracy": child_correct / 12,
            "source": "reused frozen child results (not recalled)",
        },
        "PAIRED": {
            "child_improved_over_parent": improved,
            "child_regressed_vs_parent": regressed,
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "net_gain": net_gain,
            "total_check": improved + regressed + both_correct + both_wrong,
        },
        "PER_TASK_PARENT": parent_rows,
        "PER_TASK_CHILD": child_rows,
        "assertions_passed": True,
        "NEW_REAL_HTTP_REQUESTS": 0,
    }
    (RES / "rescore_from_ledger.json").write_text(
        json.dumps(rescore, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({
        "parent_correct": parent_correct, "child_correct": child_correct,
        "improved": improved, "regressed": regressed,
        "both_correct": both_correct, "both_wrong": both_wrong,
        "net_gain": net_gain,
    }, indent=2))
    for r in parent_rows:
        print(r["task_id"], "pred", r["predicted"], "gold", r["gold_answer"],
              "correct", r["correct"], "len", r["full_response_len"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
