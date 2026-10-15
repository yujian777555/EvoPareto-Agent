"""Canonical game identity + manifest lock (Pilot1 microfix)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def canonical_game_id(game_id: str) -> str:
    """Normalize trial-dir vs game.tw-pddl forms to a stable identity."""
    p = str(game_id).replace("\\", "/").rstrip("/")
    if p.endswith("/game.tw-pddl"):
        p = p[: -len("/game.tw-pddl")]
    if p.endswith(".tw-pddl"):
        p = p[: -len(".tw-pddl")]
    return p


def manifest_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_manifest(path: str | Path) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "tasks" not in data:
        raise ValueError("manifest schema invalid: missing tasks")
    tasks = data.get("tasks") or []
    if not tasks:
        raise ValueError("manifest has no tasks")
    return data


def select_task(manifest: Dict[str, Any], task_index: int = 0) -> Dict[str, Any]:
    tasks = manifest["tasks"]
    if task_index < 0 or task_index >= len(tasks):
        raise IndexError(f"task_index {task_index} out of range ({len(tasks)})")
    return tasks[task_index]


def resolve_game_path(task: Dict[str, Any], data_root: str) -> Path:
    gid = task.get("game_id") or ""
    if not gid:
        raise ValueError("task missing game_id")
    # task game_id may be trial dir; canonical game file is game.tw-pddl
    p = Path(gid)
    if p.suffix == ".tw-pddl" or str(p).endswith("game.tw-pddl"):
        game_file = p
    else:
        game_file = p / "game.tw-pddl"
    if not game_file.exists():
        raise FileNotFoundError(f"game file not found: {game_file}")
    return game_file


def assert_task_in_split(task: Dict[str, Any], split: str) -> None:
    gid = str(task.get("game_id") or "")
    marker = f"/json_2.1.1/{split}/"
    if marker not in gid.replace("\\", "/"):
        raise ValueError(f"task {gid} not in split {split}")


def verify_actual_matches_target(actual_game_id: str, target_game_id: str) -> Tuple[str, str]:
    a = canonical_game_id(actual_game_id)
    t = canonical_game_id(target_game_id)
    if a != t:
        raise RuntimeError(f"game identity mismatch: actual={a!r} target={t!r}")
    return a, t
