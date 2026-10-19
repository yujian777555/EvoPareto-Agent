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
EXPECTED_RUN_ID = "parentre-8aa3d61f"

# Integrity manifest: SHA-256 of every frozen input. Any change must fail closed.
# Populated at first run and enforced afterwards.
INTEGRITY_MANIFEST_NAME = "rescore_input_integrity.json"


REQUIRED_INPUTS = (
    "parentre_ledger_parentre-8aa3d61f.json",
    "paired_confirmation_set.json",
    "paired_experiment_results_corrected.json",
    "parent_reverification_results.json",
)


def byte_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_input_shas(res_dir: Path) -> dict:
    shas = {}
    for rel in REQUIRED_INPUTS:
        f = res_dir / rel
        if f.exists():
            shas[rel] = byte_sha256(f)
    return shas


def init_integrity_manifest(res_dir: Path) -> dict:
    """EXPLICIT one-time manifest creation. Not called by normal rescore."""
    manifest_path = res_dir / INTEGRITY_MANIFEST_NAME
    if manifest_path.exists():
        raise RuntimeError(f"MANIFEST_ALREADY_EXISTS:{manifest_path} — refusing to reset")
    current = compute_input_shas(res_dir)
    missing = sorted(set(REQUIRED_INPUTS) - set(current))
    if missing:
        raise FileNotFoundError(f"MISSING_INPUT_FILES:{missing}")
    manifest_path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def verify_input_integrity(res_dir: Path) -> dict:
    current = compute_input_shas(res_dir)
    missing_inputs = sorted(set(REQUIRED_INPUTS) - set(current))
    if missing_inputs:
        raise FileNotFoundError(f"MISSING_INPUT_FILES:{missing_inputs}")
    manifest_path = res_dir / INTEGRITY_MANIFEST_NAME
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"INTEGRITY_MANIFEST_MISSING:{manifest_path} — run init_integrity_manifest() explicitly"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"INTEGRITY_MANIFEST_UNPARSEABLE:{e}") from e
    if not isinstance(manifest, dict) or not manifest:
        raise RuntimeError("INTEGRITY_MANIFEST_EMPTY")
    manifest_keys = set(manifest)
    required_keys = set(REQUIRED_INPUTS)
    missing_entries = sorted(required_keys - manifest_keys)
    extra_entries = sorted(manifest_keys - required_keys)
    if missing_entries:
        raise RuntimeError(f"MANIFEST_MISSING_ENTRIES:{missing_entries}")
    if extra_entries:
        raise RuntimeError(f"MANIFEST_UNAUTHORIZED_ENTRIES:{extra_entries}")
    mismatches = {}
    for rel in REQUIRED_INPUTS:
        if current.get(rel) != manifest[rel]:
            mismatches[rel] = {"expected": manifest[rel], "actual": current.get(rel)}
    if mismatches:
        raise RuntimeError(f"INPUT_HASH_MISMATCH:{mismatches}")
    return current


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
    # ---- fail-closed input loading ----
    for path, label in ((LEDGER, "LEDGER"), (CONF, "CONF"), (CORRECTED, "CORRECTED")):
        if not path.exists():
            print(f"MISSING_INPUT:{label}:{path}")
            return 2
    try:
        ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
        conf = json.loads(CONF.read_text(encoding="utf-8"))
        corrected = json.loads(CORRECTED.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"INPUT_PARSE_FAILED:{type(e).__name__}:{e}")
        return 2

    # integrity manifest (fail-closed on hash change)
    try:
        input_shas = verify_input_integrity(RES)
    except Exception as e:
        print(f"INTEGRITY_CHECK_FAILED:{e}")
        return 2

    # task-set hash: recompute from the ACTUAL task content, not the declared field
    recomputed_task_hash = sha256_text(json.dumps(
        [(t["task_id"], t["question"], t["gold_answer"]) for t in conf["tasks"]],
        sort_keys=True,
    ))
    if recomputed_task_hash != EXPECTED_TASK_HASH:
        print(f"TASK_SET_HASH_MISMATCH:recomputed={recomputed_task_hash} expected={EXPECTED_TASK_HASH}")
        return 2
    if conf.get("task_set_sha256") != EXPECTED_TASK_HASH:
        print(f"TASK_SET_DECLARED_HASH_MISMATCH:{conf.get('task_set_sha256')}")
        return 2

    rows = ledger["rows"]
    tasks = conf["tasks"]
    child_by_id = {r["task_id"]: r for r in corrected.get("PER_TASK", []) if r["role"] == "child"}

    # mandatory parent_reverification_results.json
    rev_path = RES / "parent_reverification_results.json"
    if not rev_path.exists():
        print(f"MISSING_INPUT:parent_reverification_results:{rev_path}")
        return 2
    try:
        rev = json.loads(rev_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"REVERIFICATION_PARSE_FAILED:{e}")
        return 2
    per_task_rev = rev.get("PER_TASK_PARENT") or rev.get("PER_TASK") or []
    if len(per_task_rev) != 12:
        print(f"REVERIFICATION_INCOMPLETE:n={len(per_task_rev)} expected=12")
        return 2
    rev_ids = [r.get("task_id") for r in per_task_rev]
    conf_ids = [t["task_id"] for t in tasks]
    if rev_ids != conf_ids:
        print(f"REVERIFICATION_ORDER_MISMATCH:rev={rev_ids} conf={conf_ids}")
        return 2
    for r in per_task_rev:
        if r.get("ipc_processed") != 1:
            print(f"IPC_COUNT_NOT_ONE:{r.get('task_id')}={r.get('ipc_processed')}")
            return 2
        rev_rid = r.get("run_id")
        if rev_rid is not None and rev_rid != EXPECTED_RUN_ID:
            print(f"REVERIFICATION_RUN_ID_MISMATCH:{r.get('task_id')}={rev_rid}")
            return 2
    if rev.get("task_set_sha256") and rev.get("task_set_sha256") != EXPECTED_TASK_HASH:
        print(f"REVERIFICATION_TASKSET_HASH_MISMATCH:{rev.get('task_set_sha256')}")
        return 2

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
    # run id: non-empty, consistent, and matching the expected prefix.
    # (len(set)==1 alone is insufficient: all-empty would also be a singleton.)
    run_ids = {r.get("run_id") for r in rows}
    mapping_ok = mapping_ok and len(run_ids) == 1
    only_rid = next(iter(run_ids)) if run_ids else None
    mapping_ok = mapping_ok and (only_rid == EXPECTED_RUN_ID)
    mapping_ok = mapping_ok and all(r.get("run_id") == EXPECTED_RUN_ID for r in rows)
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
    # child results must carry complete prediction + correctness evidence
    for r in corrected.get("PER_TASK", []):
        if r.get("role") != "child":
            continue
        pred = r.get("predicted_rescored") if "predicted_rescored" in r else r.get("predicted")
        corr = r.get("correct_rescored") if "correct_rescored" in r else r.get("correct")
        if pred is None or corr is None:
            print(f"CHILD_RESULT_INCOMPLETE:{r.get('task_id')} pred={pred} correct={corr}")
            return 2
        # stored correctness must agree with predicted vs gold
        gold = r.get("gold_answer") or next(
            (t["gold_answer"] for t in tasks if t["task_id"] == r.get("task_id")), None
        )
        recomputed_correct = str(pred) == str(gold) if pred is not None and gold is not None else None
        if recomputed_correct is not None and bool(corr) != recomputed_correct:
            print(f"CHILD_CORRECTNESS_CONFLICT:{r.get('task_id')} stored={corr} recomputed={recomputed_correct}")
            return 2
    # child hash cross-check with corrected file metadata
    if corrected.get("child_graph_sha256") != EXPECTED_CHILD_SHA:
        print(f"CHILD_SHA_MISMATCH:{corrected.get('child_graph_sha256')}")
        return 2
    if corrected.get("task_set_sha256") != EXPECTED_TASK_HASH:
        print(f"CHILD_TASKSET_HASH_MISMATCH:{corrected.get('task_set_sha256')}")
        return 2

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
