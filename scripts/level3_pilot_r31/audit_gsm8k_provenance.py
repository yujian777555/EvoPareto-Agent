"""Reproducible, offline GSM8K provenance audit.

The pure audit path only reads inputs and returns a report. The CLI writes the
derived report artifact, but never changes the original R3 task set/results or
the authorization ledger.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results" / "level3_pilot_r31"
RES3 = ROOT / "results" / "level3_pilot_r3"

EXPECTED_OFFICIAL_SHA = "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
EXPECTED_RECORD_COUNT = 1319
EXPECTED_R3_TASK_COUNT = 35
DEFAULT_OFFICIAL_PATH = AUDIT / "gsm8k_test_official.jsonl"
DEFAULT_R3_PATH = RES3 / "paired_confirmation_set_35.json"
DEFAULT_OUTPUT_PATH = AUDIT / "dataset_provenance_audit.json"
OFFICIAL_SOURCE = (
    "https://github.com/openai/grade-school-math/blob/master/"
    "grade_school_math/data/test.jsonl"
)


def normalize_text(s: str) -> str:
    """Collapse whitespace runs to one space; otherwise preserve exact text."""
    return " ".join(s.split())


def extract_gold(answer: str) -> str | None:
    """Extract the final answer after the last GSM8K '####' marker."""
    if "####" in answer:
        return answer.rsplit("####", 1)[1].strip()
    return None


def audit_task_rows(r3_tasks, official):
    """Compare every R3 task with official question text AND extracted gold."""
    official_by_question = {}
    for i, rec in enumerate(official):
        question = rec.get("question")
        if not isinstance(question, str):
            raise ValueError(f"OFFICIAL_QUESTION_INVALID:{i}")
        official_by_question.setdefault(normalize_text(question), []).append((i, rec))

    rows = []
    for task in r3_tasks:
        if not isinstance(task, dict):
            raise ValueError("R3_TASK_RECORD_INVALID")
        task_id = task.get("task_id")
        question = task.get("question")
        declared_gold = task.get("gold_answer")
        if not isinstance(question, str) or declared_gold is None:
            raise ValueError(f"R3_TASK_FIELDS_INVALID:{task_id}")
        matches = official_by_question.get(normalize_text(question), [])
        if not matches:
            rows.append({
                "task_id": task_id,
                "declared_index": task.get("index"),
                "question_match": "NO_MATCH",
                "official_index": None,
                "gold_match": None,
                "declared_gold": declared_gold,
                "official_gold": None,
                "final_status": "SYNTHETIC_OR_UNMATCHED",
            })
            continue

        candidates = []
        for index, rec in matches:
            answer = rec.get("answer")
            if not isinstance(answer, str):
                raise ValueError(f"OFFICIAL_ANSWER_INVALID:{index}")
            candidates.append((index, extract_gold(answer)))
        normalized_declared_gold = normalize_text(str(declared_gold))
        exact_gold = [
            (index, gold) for index, gold in candidates
            if gold is not None and normalize_text(gold) == normalized_declared_gold
        ]
        available_gold = [(index, gold) for index, gold in candidates if gold is not None]
        if exact_gold:
            official_index, official_gold = exact_gold[0]
            status = "OFFICIAL_MATCH"
            gold_match = True
        elif available_gold:
            official_index, official_gold = available_gold[0]
            status = "GOLD_MISMATCH"
            gold_match = False
        else:
            # Text alone is insufficient: never promote a task without a gold answer.
            official_index, official_gold = matches[0][0], None
            status = "GOLD_UNVERIFIED"
            gold_match = None
        rows.append({
            "task_id": task_id,
            "declared_index": task.get("index"),
            "question_match": "EXACT",
            "official_index": official_index,
            "gold_match": gold_match,
            "declared_gold": declared_gold,
            "official_gold": official_gold,
            "final_status": status,
        })
    return rows


def audit_provenance(
    official_path=DEFAULT_OFFICIAL_PATH,
    r3_path=DEFAULT_R3_PATH,
    output_path=None,
):
    """Verify pinned source and audit R3 tasks. Writes only if output_path is set."""
    official_path = Path(official_path)
    r3_path = Path(r3_path)
    raw = official_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_OFFICIAL_SHA:
        raise ValueError(f"OFFICIAL_FILE_SHA_MISMATCH:{sha}")

    official = []
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"OFFICIAL_RECORD_INVALID:{line_number}")
        if not isinstance(record.get("question"), str) or not isinstance(record.get("answer"), str):
            raise ValueError(f"OFFICIAL_RECORD_SCHEMA_INVALID:{line_number}")
        official.append(record)
    if len(official) != EXPECTED_RECORD_COUNT:
        raise ValueError(
            f"OFFICIAL_RECORD_COUNT_MISMATCH:{len(official)} expected={EXPECTED_RECORD_COUNT}"
        )

    r3 = json.loads(r3_path.read_text(encoding="utf-8"))
    if not isinstance(r3, dict) or not isinstance(r3.get("tasks"), list):
        raise ValueError("R3_TASKSET_SCHEMA_INVALID")
    r3_tasks = r3["tasks"]
    if len(r3_tasks) != EXPECTED_R3_TASK_COUNT:
        raise ValueError(
            f"R3_TASK_COUNT_MISMATCH:{len(r3_tasks)} expected={EXPECTED_R3_TASK_COUNT}"
        )
    for task in r3_tasks:
        if not isinstance(task, dict):
            raise ValueError("R3_TASK_RECORD_INVALID")
        if not isinstance(task.get("question"), str) or task.get("gold_answer") is None:
            raise ValueError(f"R3_TASK_FIELDS_INVALID:{task.get('task_id')}")

    rows = audit_task_rows(r3_tasks, official)
    counts = {
        "official_match_count": sum(r["final_status"] == "OFFICIAL_MATCH" for r in rows),
        "synthetic_or_unmatched_count": sum(r["final_status"] == "SYNTHETIC_OR_UNMATCHED" for r in rows),
        "gold_mismatch_count": sum(r["final_status"] == "GOLD_MISMATCH" for r in rows),
        "gold_unverified_count": sum(r["final_status"] == "GOLD_UNVERIFIED" for r in rows),
    }
    if sum(counts.values()) != len(r3_tasks):
        raise ValueError("AUDIT_OUTPUT_COUNT_MISMATCH")

    summary = {
        "evidence_class": "REPRODUCIBLE_OFFLINE_AUDIT",
        "normalization": "collapse whitespace runs to one space; otherwise exact text match",
        "gold_extraction": "text after last '####' marker; whitespace-normalized exact comparison",
        "official_source": OFFICIAL_SOURCE,
        "official_file_sha256": sha,
        "official_record_count": len(official),
        "r3_task_count": len(r3_tasks),
        **counts,
        "rows": rows,
        "conclusion": (
            f"{counts['official_match_count']}/{len(r3_tasks)} match both official question and gold; "
            f"{counts['synthetic_or_unmatched_count']} synthetic/unmatched; provenance NOT verified."
        ),
    }
    if output_path is not None:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> int:
    try:
        summary = audit_provenance(output_path=DEFAULT_OUTPUT_PATH)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(str(exc))
        return 2
    print(json.dumps({
        key: summary[key] for key in (
            "official_record_count", "r3_task_count", "official_match_count",
            "synthetic_or_unmatched_count", "gold_mismatch_count", "gold_unverified_count",
        )
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
