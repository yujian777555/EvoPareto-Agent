"""Safe archive audit + extract for AFlow results.tar.gz."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import tarfile
from pathlib import Path

SRC = Path(r"C:\Users\于舰\Downloads\results.tar.gz")
DEST = Path(__file__).resolve().parents[2] / "external" / "AFlow_results"
OUT = Path(__file__).resolve().parents[2] / "results" / "stage3_0_p1_r2"
OUT.mkdir(parents=True, exist_ok=True)

report = {
    "source_path": str(SRC),
    "size_bytes": SRC.stat().st_size,
    "sha256": hashlib.sha256(SRC.read_bytes()).hexdigest().upper(),
    "format_detected": "",
    "integrity": "",
    "path_traversal_findings": [],
    "symlinks": [],
    "extracted_file_count": 0,
    "extracted_total_bytes": 0,
    "sample_paths": [],
    "status": "PENDING",
}

# format detection
with open(SRC, "rb") as f:
    magic = f.read(4)
if magic[:2] == b"\x1f\x8b":
    report["format_detected"] = "gzip"
    try:
        with gzip.open(SRC, "rb") as g:
            head = g.read(512)
        report["format_detected"] = "gzip; inner=" + ("tar" if head[257:261] == b"ustar" else head[:8].hex())
    except Exception as e:
        report["integrity"] = f"gzip open error: {e}"
else:
    report["format_detected"] = magic.hex()

# integrity + safety listing (no extract yet)
bad = []
members = []
try:
    with tarfile.open(SRC, "r:gz") as tf:
        for m in tf.getmembers():
            members.append(m.name)
            if m.name.startswith("/") or ".." in Path(m.name).parts:
                report["path_traversal_findings"].append(m.name)
            if m.issym() or m.islnk():
                report["symlinks"].append(m.name)
            if m.size > 50_000_000:
                report["path_traversal_findings"].append(f"HUGE:{m.name}:{m.size}")
    report["integrity"] = f"OK ({len(members)} members)"
except Exception as e:
    report["integrity"] = f"FAIL: {e}"

# extract only if clean
if report["integrity"].startswith("OK") and not report["path_traversal_findings"] and not report["symlinks"]:
    DEST.mkdir(parents=True, exist_ok=True)
    with tarfile.open(SRC, "r:gz") as tf:
        tf.extractall(DEST)
    files = [p for p in DEST.rglob("*") if p.is_file()]
    report["extracted_file_count"] = len(files)
    report["extracted_total_bytes"] = sum(p.stat().st_size for p in files)
    report["sample_paths"] = [str(p.relative_to(DEST)) for p in sorted(files)[:30]]
    report["status"] = "EXTRACTED"
else:
    report["status"] = "BLOCKED"

(OUT / "archive_audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({k: report[k] for k in ("size_bytes","sha256","format_detected","integrity","extracted_file_count","status")}, indent=2))
