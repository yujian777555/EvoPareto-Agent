"""Task content fingerprints and held-out leakage detection (Phase5-R3-R1).

Different task_id suffixes with the same template are NOT independent tasks.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


def task_fingerprint(task: Dict[str, Any]) -> str:
    """Stable hash of task *content* (ignore run-specific suffixes)."""
    core = {
        "goal": task.get("goal", ""),
        "template_id": task.get("template_id") or task.get("task_id", "").rsplit("-", 3)[0],
        "difficulty": float(task.get("difficulty", 0.0)),
        "required_tool": task.get("required_tool") or task.get("required_tools"),
        "hint": task.get("hint", ""),
        "category": task.get("category", ""),
        "horizon": task.get("horizon"),
    }
    raw = "|".join(str(core[k]) for k in sorted(core))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def split_by_fingerprint(
    tasks: Sequence[Dict[str, Any]],
    *,
    train_frac: float = 0.7,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split unique task contents (not task_ids) into train/test."""
    if not tasks:
        return [], []
    seen: Dict[str, Dict[str, Any]] = {}
    for t in tasks:
        fp = task_fingerprint(t)
        if fp not in seen:
            seen[fp] = t
    unique = list(seen.values())
    n_train = max(1, int(len(unique) * train_frac))
    if len(unique) >= 2:
        n_train = min(n_train, len(unique) - 1)
    train_fp = {task_fingerprint(t) for t in unique[:n_train]}
    train = [t for t in tasks if task_fingerprint(t) in train_fp]
    test = [t for t in tasks if task_fingerprint(t) not in train_fp]
    return train, test


@dataclass
class LeakReport:
    ok: bool
    n_train: int
    n_test: int
    overlap_fingerprints: List[str]
    message: str

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "overlap_fingerprints": self.overlap_fingerprints,
            "message": self.message,
        }


def detect_task_leakage(
    train_tasks: Sequence[Dict[str, Any]],
    test_tasks: Sequence[Dict[str, Any]],
) -> LeakReport:
    """FAIL if train and test share any content fingerprint."""
    tr = {task_fingerprint(t) for t in train_tasks}
    te = {task_fingerprint(t) for t in test_tasks}
    overlap = sorted(tr & te)
    ok = len(overlap) == 0 and len(te) > 0 and len(tr) > 0
    msg = (
        "content-level isolation OK"
        if ok
        else f"LEAK: {len(overlap)} shared fingerprints; independent test NOT available"
    )
    return LeakReport(ok, len(tr), len(te), overlap, msg)


def assert_no_content_leakage(
    train_tasks: Sequence[Dict[str, Any]],
    test_tasks: Sequence[Dict[str, Any]],
) -> LeakReport:
    rep = detect_task_leakage(train_tasks, test_tasks)
    if not rep.ok:
        raise RuntimeError(f"task content leakage: {rep.message}")
    return rep


def is_same_template_only(task_a: Dict[str, Any], task_b: Dict[str, Any]) -> bool:
    """True if two tasks differ only by id suffix (same content)."""
    return task_fingerprint(task_a) == task_fingerprint(task_b)
