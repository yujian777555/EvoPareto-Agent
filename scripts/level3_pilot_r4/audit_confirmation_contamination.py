"""Deterministic offline confirmation-set contamination audit (R4-R3).

Re-runnable: same inputs -> same JSON (sort_keys=True). No network. No model
calls. Never writes into results/ experiment namespaces.

Verdict classes (no-hit is NOT automatically DATA_ONLY):

* ``NO_HIT``                  — question text not found in scanned corpus
* ``ALLOWED_SOURCE_ONLY``     — only in official source / freeze draft / audit self
* ``PROTOCOL_DECLARED_HIT``   — only in split-manifest / protocol declarations
* ``HISTORICAL_SCORED_HIT``   — found in scoring/ledger/replay artefacts
* ``INCONCLUSIVE_SCAN``       — scan/hash gate failed; independence blocked

Independence is ``VERIFIED`` only if official SHA/count match AND freeze hash
gates pass AND every task is NO_HIT or ALLOWED_SOURCE_ONLY. Any
HISTORICAL_SCORED_HIT or gate failure downgrades / blocks.

Usage:
    python scripts/level3_pilot_r4/audit_confirmation_contamination.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_paired_stats import canonical_task_set_sha256, verify_task_set

OFFICIAL_REL = "results/level3_pilot_r31/gsm8k_test_official.jsonl"
OFFICIAL_SHA = "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
OFFICIAL_N = 1319

EXPECTED_FREEZE_COUNT = 40
EXPECTED_V1_SHA = "1771a67ccf232984d8c79c5179ea9ff3a11001324222709308058eb9d58735b4"

SCAN_ROOTS = ("results", "docs", "scripts", "tests", "src")
SCAN_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".txt", ".csv", ".yml", ".yaml"}
EXCLUDE_DIR_NAMES = {".git", "external", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDE_PATH_SUBSTRINGS = (
    "gsm8k_test_official.jsonl",
    "confirmation_contamination_audit",
    "confirmation_set_proposed.json",
    "confirmation_set_v1_proposed.json",
)

V_NO_HIT = "NO_HIT"
V_ALLOWED = "ALLOWED_SOURCE_ONLY"
V_DECLARED = "PROTOCOL_DECLARED_HIT"
V_SCORED = "HISTORICAL_SCORED_HIT"
V_INCONCLUSIVE = "INCONCLUSIVE_SCAN"

C_OFFICIAL = "OFFICIAL_SOURCE"
C_FREEZE = "FREEZE_DRAFT"
C_SCORED = "HISTORICAL_SCORING"
C_DECLARED = "PROTOCOL_DECLARATION"
C_OTHER = "OTHER_REPO"
C_AUDIT_SELF = "AUDIT_SELF"


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_official(path: Path) -> List[Dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows.append({
                "index": i,
                "question": obj["question"],
                "question_norm": " ".join(obj["question"].split()),
                "answer": obj["answer"],
            })
    return rows


def source_class(rel: str) -> str:
    if rel.endswith("gsm8k_test_official.jsonl") or "gsm8k_test_official" in rel:
        return C_OFFICIAL
    if "freeze/confirmation_set" in rel:
        return C_FREEZE
    if "confirmation_contamination" in rel or "audit_confirmation" in rel:
        return C_AUDIT_SELF
    if "gsm8k_split_manifest" in rel or "gsm8k_protocol" in rel:
        return C_DECLARED
    if rel.startswith("results/"):
        if any(k in rel for k in (
            "paired_confirmation", "paired_experiment", "parent_reverification",
            "rescore", "ledg", "level3_pilot", "level3_live", "final_live",
        )):
            return C_SCORED
        return C_SCORED
    return C_OTHER


def fragments_for(question_norm: str) -> List[str]:
    """Deterministic match fragments: full text + 3 non-overlapping windows."""
    out = [question_norm]
    n = len(question_norm)
    if n >= 70:
        out.append(question_norm[:70])
    if n >= 140:
        out.append(question_norm[70:140])
    if n >= 80:
        out.append(question_norm[-80:])
    return [f for f in out if f]


def classify_verdict(hits: List[Dict[str, Any]], gate_ok: bool) -> str:
    if not gate_ok:
        return V_INCONCLUSIVE
    if not hits:
        return V_NO_HIT
    srcs = {h["source_class"] for h in hits}
    if C_SCORED in srcs:
        return V_SCORED
    if srcs <= {C_OFFICIAL, C_FREEZE, C_AUDIT_SELF}:
        return V_ALLOWED
    if srcs <= {C_OFFICIAL, C_FREEZE, C_AUDIT_SELF, C_DECLARED}:
        return V_DECLARED
    # mixed unknown sources — treat as inconclusive, never silently DATA_ONLY
    return V_INCONCLUSIVE


def audit(root: Path, freeze_path: Path) -> Dict[str, Any]:
    problems: List[str] = []

    official_path = root / OFFICIAL_REL
    if not official_path.exists():
        problems.append("OFFICIAL_FILE_MISSING")
        official = []
        official_sha = ""
    else:
        official_bytes = official_path.read_bytes()
        official_sha = sha256_bytes(official_bytes)
        if official_sha != OFFICIAL_SHA:
            problems.append("OFFICIAL_SHA_MISMATCH")
        try:
            official = load_official(official_path)
        except Exception as exc:
            problems.append("OFFICIAL_PARSE_ERROR:%s" % type(exc).__name__)
            official = []
        if len(official) != OFFICIAL_N:
            problems.append("OFFICIAL_COUNT_MISMATCH")

    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    tasks = freeze.get("tasks") or []
    declared_sha = freeze.get("task_set_sha256")
    recomputed_sha = canonical_task_set_sha256(tasks) if tasks else ""
    gate_err = verify_task_set(
        tasks,
        declared_sha,
        EXPECTED_V1_SHA,
        expected_count=EXPECTED_FREEZE_COUNT,
    ) if tasks else "TASKSET_EMPTY"
    freeze_gate_ok = gate_err == ""
    if not freeze_gate_ok:
        problems.append("FREEZE_GATE:%s" % gate_err)

    gate_ok = (not problems)

    qn_to_idx = {r["question_norm"]: r["index"] for r in official}

    scan_manifest = []
    texts: List[Tuple[str, str]] = []
    scan_errors: List[str] = []
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.exists():
            scan_errors.append("SCAN_ROOT_MISSING:%s" % scan_root)
            continue
        try:
            candidates = sorted(base.rglob("*"))
        except Exception as exc:
            scan_errors.append("SCAN_ROOT_ERROR:%s:%s" % (scan_root, type(exc).__name__))
            continue
        for p in candidates:
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIR_NAMES for part in p.parts):
                continue
            if p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            rel = p.relative_to(root).as_posix()
            if any(s in rel for s in EXCLUDE_PATH_SUBSTRINGS):
                continue
            try:
                raw = p.read_bytes()
            except Exception as exc:
                scan_errors.append("FILE_READ_ERROR:%s:%s" % (rel, type(exc).__name__))
                continue
            scan_manifest.append({
                "path": rel,
                "sha256": sha256_bytes(raw),
                "size": len(raw),
                "source_class": source_class(rel),
            })
            try:
                texts.append((rel, raw.decode("utf-8", errors="replace")))
            except Exception as exc:
                scan_errors.append("FILE_DECODE_ERROR:%s:%s" % (rel, type(exc).__name__))

    if scan_errors:
        problems.extend(scan_errors)

    per_task = []
    for t in tasks:
        qn = " ".join((t.get("question") or "").split())
        idx = t.get("index")
        idf = "gsm8k-official-test-%04d" % idx if isinstance(idx, int) else None
        frags = fragments_for(qn)
        hits = []
        for rel, txt in texts:
            flat = " ".join(txt.split())
            matched = [f for f in frags if f and f in flat]
            reasons = []
            if matched:
                # require the 70-char head or full text to avoid tiny-false hits
                if qn in flat or (frags[1] if len(frags) > 1 else qn) in flat:
                    reasons.append("question_text")
            if idf and idf in txt:
                reasons.append("official_task_id")
            if reasons:
                hits.append({
                    "file": rel,
                    "reasons": reasons,
                    "source_class": source_class(rel),
                    "n_frags_matched": len(matched),
                })
        verdict = classify_verdict(hits, gate_ok)
        per_task.append({
            "task_id": t.get("task_id"),
            "index": idx,
            "verdict": verdict,
            "n_hits": len(hits),
            "hits": hits,
        })

    r2_path = root / "results/level3_pilot_r2/paired_confirmation_set.json"
    r2_official_indices: List[int] = []
    if r2_path.exists():
        try:
            r2 = json.loads(r2_path.read_text(encoding="utf-8"))
            for t in r2.get("tasks", []):
                qn = " ".join(t.get("question", "").split())
                if qn in qn_to_idx:
                    r2_official_indices.append(qn_to_idx[qn])
        except Exception as exc:
            problems.append("R2_PARSE_ERROR:%s" % type(exc).__name__)

    conf_indices = [t.get("index") for t in tasks if isinstance(t.get("index"), int)]
    n_scored = sum(1 for r in per_task if r["verdict"] == V_SCORED)
    n_inconc = sum(1 for r in per_task if r["verdict"] == V_INCONCLUSIVE)
    n_allowed = sum(1 for r in per_task if r["verdict"] == V_ALLOWED)
    n_declared = sum(1 for r in per_task if r["verdict"] == V_DECLARED)
    n_nohit = sum(1 for r in per_task if r["verdict"] == V_NO_HIT)

    if not gate_ok or n_inconc > 0:
        independence = "CONFIRMATION_INDEPENDENCE_BLOCKED"
    elif n_scored > 0:
        independence = "CONFIRMATION_INDEPENDENCE_UNVERIFIED"
    else:
        independence = "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"

    return {
        "evidence_class": "REPRODUCIBLE_OFFLINE_AUDIT",
        "audit": "confirmation_set_historical_contamination",
        "script": "scripts/level3_pilot_r4/audit_confirmation_contamination.py",
        "scan_roots": list(SCAN_ROOTS),
        "scan_suffixes": sorted(SCAN_SUFFIXES),
        "exclude_dir_names": sorted(EXCLUDE_DIR_NAMES),
        "exclude_path_substrings": list(EXCLUDE_PATH_SUBSTRINGS),
        "official_baseline": {
            "file": OFFICIAL_REL,
            "sha256": official_sha,
            "sha256_expected": OFFICIAL_SHA,
            "sha256_match": official_sha == OFFICIAL_SHA,
            "record_count": len(official),
            "record_count_expected": OFFICIAL_N,
            "record_count_match": len(official) == OFFICIAL_N,
        },
        "freeze_gate": {
            "file": str(freeze_path.relative_to(root).as_posix()),
            "declared_sha256": declared_sha,
            "recomputed_sha256": recomputed_sha,
            "expected_sha256": EXPECTED_V1_SHA,
            "expected_count": EXPECTED_FREEZE_COUNT,
            "verify_error": gate_err,
            "ok": freeze_gate_ok,
        },
        "scan_errors": scan_errors,
        "problems": problems,
        "gate_ok": gate_ok,
        "scan_file_count": len(scan_manifest),
        "scan_manifest": scan_manifest,
        "summary": {
            "n_tasks": len(tasks),
            "n_no_hit": n_nohit,
            "n_allowed_source_only": n_allowed,
            "n_protocol_declared": n_declared,
            "n_historical_scored": n_scored,
            "n_inconclusive": n_inconc,
            "r2_prior_scored_official_indices": sorted(r2_official_indices),
            "overlap_with_confirmation": sorted(set(r2_official_indices) & set(conf_indices)),
        },
        "per_task": per_task,
        "independence": independence,
        "notes": [
            "NO_HIT is not DATA_ONLY. Allowed sources are official file, freeze draft, audit self.",
            "HISTORICAL_SCORED_HIT downgrades independence; gate failure blocks it.",
            "No performance-based selection or exclusion is applied.",
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--freeze",
        default="docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json",
    )
    ap.add_argument(
        "--out",
        default="docs/level3_pilot_r4_design/confirmation_contamination_audit_rerun.json",
    )
    args = ap.parse_args(argv)
    report = audit(ROOT, ROOT / args.freeze)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)
    out_path.write_text(text + "\n", encoding="utf-8")
    print("wrote", out_path)
    print("official_sha_match", report["official_baseline"]["sha256_match"])
    print("official_n_match", report["official_baseline"]["record_count_match"])
    print("freeze_gate_ok", report["freeze_gate"]["ok"], report["freeze_gate"]["verify_error"])
    print("independence", report["independence"])
    print("summary", json.dumps(report["summary"], sort_keys=True))
    print("problems", report["problems"])
    if not report["official_baseline"]["sha256_match"] or not report["official_baseline"]["record_count_match"]:
        return 2
    if not report["gate_ok"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
