"""Reproducible GSM8K provenance audit (Task C)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:/新建文件夹")

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "results" / "level3_pilot_r31"
RES3 = ROOT / "results" / "level3_pilot_r3"

EXPECTED_OFFICIAL_SHA = "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
EXPECTED_RECORD_COUNT = 1319


def normalize_text(s: str) -> str:
    """Whitespace normalization: collapse all whitespace runs to single spaces."""
    return " ".join(s.split())


def extract_gold(answer: str) -> str | None:
    if "####" in answer:
        return answer.rsplit("####", 1)[1].strip()
    return None


def main() -> int:
    official_path = AUDIT / "gsm8k_test_official.jsonl"
    if not official_path.exists():
        print(f"OFFICIAL_FILE_MISSING:{official_path}")
        return 2

    raw = official_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != EXPECTED_OFFICIAL_SHA:
        print(f"OFFICIAL_FILE_SHA_MISMATCH:{sha}")
        return 2

    official = []
    for line in raw.decode("utf-8").strip().split("\n"):
        if line.strip():
            official.append(json.loads(line))
    if len(official) != EXPECTED_RECORD_COUNT:
        print(f"OFFICIAL_RECORD_COUNT_MISMATCH:{len(official)} expected={EXPECTED_RECORD_COUNT}")
        return 2

    r3 = json.loads((RES3 / "paired_confirmation_set_35.json").read_text(encoding="utf-8"))
    r3_tasks = r3["tasks"]

    audit_rows = []
    for t in r3_tasks:
        q_norm = normalize_text(t["question"])
        matched_idx = None
        matched_gold = None
        for i, rec in enumerate(official):
            if normalize_text(rec["question"]) == q_norm:
                matched_idx = i
                matched_gold = extract_gold(rec.get("answer", ""))
                break
        is_official = matched_idx is not None
        gold_match = None
        if is_official:
            gold_match = str(matched_gold) == str(t["gold_answer"]) if matched_gold is not None else None
        status = (
            "OFFICIAL_MATCH" if is_official and gold_match is not False
            else "GOLD_MISMATCH" if is_official
            else "SYNTHETIC_OR_UNMATCHED"
        )
        audit_rows.append({
            "task_id": t["task_id"],
            "declared_index": t.get("index"),
            "question_match": "EXACT" if is_official else "NO_MATCH",
            "official_index": matched_idx,
            "gold_match": gold_match,
            "declared_gold": t["gold_answer"],
            "official_gold": matched_gold,
            "final_status": status,
        })

    n_official = sum(1 for r in audit_rows if r["final_status"] == "OFFICIAL_MATCH")
    n_synth = sum(1 for r in audit_rows if r["final_status"] == "SYNTHETIC_OR_UNMATCHED")
    n_gold = sum(1 for r in audit_rows if r["final_status"] == "GOLD_MISMATCH")

    summary = {
        "evidence_class": "REPRODUCIBLE_OFFLINE_AUDIT",
        "normalization": "whitespace collapse to single spaces; exact text match",
        "gold_extraction": "text after last '####' marker in official answer field",
        "official_source": "https://github.com/openai/grade-school-math",
        "official_file_sha256": sha,
        "official_record_count": len(official),
        "r3_task_count": len(r3_tasks),
        "official_match_count": n_official,
        "synthetic_or_unmatched_count": n_synth,
        "gold_mismatch_count": n_gold,
        "rows": audit_rows,
        "conclusion": f"{n_official}/{len(r3_tasks)} match official; {n_synth} synthetic/unmatched. Provenance NOT verified.",
    }
    (AUDIT / "dataset_provenance_audit.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: summary[k] for k in ["official_record_count", "r3_task_count", "official_match_count", "synthetic_or_unmatched_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
