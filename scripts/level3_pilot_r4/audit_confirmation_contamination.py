"""Deterministic offline confirmation-set contamination audit (R4-R2).

Re-runnable: same inputs -> same JSON output (byte-stable field order).
No network. No model calls. Never writes into results/ experiment namespaces.

Usage:
    python scripts/level3_pilot_r4/audit_confirmation_contamination.py \
        --out docs/level3_pilot_r4_design/confirmation_contamination_audit_rerun.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OFFICIAL_REL = "results/level3_pilot_r31/gsm8k_test_official.jsonl"
OFFICIAL_SHA = "3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14"
OFFICIAL_N = 1319

# Scan scope (frozen). Relative to repo root.
SCAN_ROOTS = ("results", "docs", "scripts", "tests", "src")
SCAN_SUFFIXES = {".json", ".jsonl", ".md", ".py", ".txt", ".csv", ".yml", ".yaml"}
EXCLUDE_DIR_NAMES = {".git", "external", "__pycache__", "node_modules", ".pytest_cache"}
EXCLUDE_PATH_SUBSTRINGS = (
    "gsm8k_test_official.jsonl",  # source of truth
    "confirmation_contamination_audit",  # prior audit outputs
    "confirmation_set_proposed.json",  # freeze drafts (self-hit)
    "confirmation_set_v1_proposed.json",
)

CLASS_DATA_ONLY = "DATA_ONLY"
CLASS_SCORED = "SCORED_OR_SELECTED"
CLASS_DECLARED = "DECLARED_ONLY"


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


def load_freeze(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_scan_files(root: Path) -> List[Tuple[str, Path]]:
    out: List[Tuple[str, Path]] = []
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file():
                continue
            if any(part in EXCLUDE_DIR_NAMES for part in p.parts):
                continue
            if p.suffix.lower() not in SCAN_SUFFIXES:
                continue
            rel = p.relative_to(root).as_posix()
            if any(s in rel for s in EXCLUDE_PATH_SUBSTRINGS):
                continue
            out.append((rel, p))
    return out


def classify_hit(rel: str, reasons: List[str]) -> str:
    if rel.startswith("results/level3_pilot_r31/gsm8k_test_official"):
        return CLASS_DATA_ONLY
    if rel.startswith("docs/level3_pilot_r4_design/freeze/"):
        return CLASS_DATA_ONLY
    # R2/R3 confirmation sets and ledgers = scoring artefacts
    if any(k in rel for k in (
        "paired_confirmation",
        "paired_experiment",
        "parent_reverification",
        "rescore_from_ledger",
        "ledg",
        "results/level3_pilot",
    )):
        return CLASS_SCORED
    if "gsm8k_split_manifest" in rel or "gsm8k_protocol" in rel:
        return CLASS_DECLARED
    if rel.startswith("results/"):
        return CLASS_SCORED
    return CLASS_DATA_ONLY


def audit(root: Path, freeze_path: Path) -> Dict[str, Any]:
    official_path = root / OFFICIAL_REL
    official_bytes = official_path.read_bytes()
    official_sha = sha256_bytes(official_bytes)
    official = load_official(official_path)
    freeze = load_freeze(freeze_path)
    tasks = freeze["tasks"]

    # index map from official
    qn_to_idx = {r["question_norm"]: r["index"] for r in official}

    scan_files = iter_scan_files(root)
    scan_manifest = []
    texts: List[Tuple[str, str]] = []
    for rel, p in scan_files:
        raw = p.read_bytes()
        entry = {
            "path": rel,
            "sha256": sha256_bytes(raw),
            "size": len(raw),
        }
        scan_manifest.append(entry)
        try:
            texts.append((rel, raw.decode("utf-8", errors="replace")))
        except Exception:
            pass

    per_task = []
    for t in tasks:
        frag = " ".join(t["question"].split())[:70]
        idx = t["index"]
        idf = "gsm8k-official-test-%04d" % idx
        hits = []
        for rel, txt in texts:
            reasons = []
            flat = " ".join(txt.split())
            if frag and frag in flat:
                reasons.append("question_frag")
            if idf in txt:
                reasons.append("official_task_id")
            if reasons:
                hits.append({
                    "file": rel,
                    "reasons": reasons,
                    "classification": classify_hit(rel, reasons),
                })
        # historical R2 official index use is recorded separately (by question match)
        classes = [h["classification"] for h in hits]
        if CLASS_SCORED in classes:
            verdict = "CONTAMINATED_SCORED"
        elif any(h["classification"] == CLASS_DATA_ONLY for h in hits) and CLASS_SCORED not in classes:
            verdict = "DATA_ONLY"
        elif CLASS_DECLARED in classes and CLASS_SCORED not in classes:
            verdict = "DECLARED_ONLY"
        else:
            verdict = "DATA_ONLY"
        per_task.append({
            "task_id": t["task_id"],
            "index": idx,
            "verdict": verdict,
            "n_hits": len(hits),
            "hits": hits,
        })

    # R2 official indices used for scoring (via question text match)
    r2_path = root / "results/level3_pilot_r2/paired_confirmation_set.json"
    r2_official_indices = []
    if r2_path.exists():
        r2 = json.loads(r2_path.read_text(encoding="utf-8"))
        for t in r2.get("tasks", []):
            qn = " ".join(t.get("question", "").split())
            if qn in qn_to_idx:
                r2_official_indices.append(qn_to_idx[qn])

    conf_indices = [t["index"] for t in tasks]
    summary = {
        "n_tasks": len(tasks),
        "n_data_only": sum(1 for r in per_task if r["verdict"] == "DATA_ONLY"),
        "n_scored_or_selected": sum(1 for r in per_task if r["verdict"] == "CONTAMINATED_SCORED"),
        "n_declared_only": sum(1 for r in per_task if r["verdict"] == "DECLARED_ONLY"),
        "r2_prior_scored_official_indices": sorted(r2_official_indices),
        "overlap_with_confirmation": sorted(set(r2_official_indices) & set(conf_indices)),
    }

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
        "freeze_file": str(freeze_path.relative_to(root).as_posix()),
        "freeze_task_set_sha256": freeze.get("task_set_sha256"),
        "scan_file_count": len(scan_manifest),
        "scan_manifest": scan_manifest,
        "summary": summary,
        "per_task": per_task,
        "independence": (
            "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"
            if summary["n_scored_or_selected"] == 0
            else "CONFIRMATION_INDEPENDENCE_UNVERIFIED"
        ),
        "notes": [
            "DATA_ONLY = question text only in official source / freeze draft / this audit's excluded copies",
            "SCORED_OR_SELECTED = found under results/ experiment artefacts",
            "DECLARED_ONLY = split-manifest / protocol index declarations",
            "No performance-based selection or exclusion is applied here.",
        ],
    }


def main(argv: List[str] | None = None) -> int:
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
    print("independence", report["independence"])
    print("summary", json.dumps(report["summary"], sort_keys=True))
    print("scan_file_count", report["scan_file_count"])
    return 0 if report["official_baseline"]["sha256_match"] and report["official_baseline"]["record_count_match"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

