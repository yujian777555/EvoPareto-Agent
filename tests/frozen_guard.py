"""Frozen results integrity guard (Stage 3.0-P1-R2A-R1 Task 1).

Source-of-truth helper used by conftest and regression tests. Hashes every
tracked file under results/ so that any test-time write to a frozen experiment
record is detected immediately — not repaired afterwards with git checkout.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]


def tracked_results_files() -> List[str]:
    """All git-tracked files under results/ (frozen experiment records)."""
    out = subprocess.check_output(
        ["git", "ls-files", "-z", "results/"], cwd=str(ROOT), text=False
    )
    return sorted(
        p.decode("utf-8").replace("\\", "/")
        for p in out.split(b"\x00")
        if p and p.decode("utf-8").replace("\\", "/") != "results/"
    )


def snapshot(results_root: Path | None = None) -> Dict[str, str]:
    """SHA-256 of every tracked results/ file (missing files -> None marker)."""
    snap: Dict[str, str] = {}
    for rel in tracked_results_files():
        path = (results_root or ROOT) / rel
        if not path.exists():
            snap[rel] = "MISSING"
        else:
            snap[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snap


def diff(before: Dict[str, str], after: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    return added, removed, modified


def assert_frozen_unchanged(before: Dict[str, str], after: Dict[str, str]) -> None:
    added, removed, modified = diff(before, after)
    if added or removed or modified:
        raise AssertionError(
            "frozen experiment results were modified by tests:\n"
            f"  added={added}\n  removed={removed}\n  modified={modified}"
        )


def write_snapshot(path: Path, snap: Dict[str, str], *, meta: Dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "evidence_class": "MOCK_TEST",
        "n_files": len(snap),
        "sha256": snap,
    }
    if meta:
        payload["meta"] = meta
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
