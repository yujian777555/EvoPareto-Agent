"""Build development task pool + frozen test manifest (Phase5-R3-R4 Task2)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List


def fingerprint(game_id: str, goal: str) -> str:
    raw = f"{game_id}|{goal}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def scan_split(data_root: str, split: str, limit: int = 40) -> List[Dict[str, Any]]:
    root = Path(data_root) / "json_2.1.1" / split
    if not root.is_dir():
        return []
    items = []
    for p in sorted(root.rglob("traj_data.json"))[:limit]:
        game_dir = p.parent
        game_file = game_dir / "game.tw-pddl"
        task_type = game_dir.parent.name  # type folder name
        goal = ""
        try:
            import json as _j

            traj = _j.loads(p.read_text(encoding="utf-8", errors="replace"))
            goal = str(traj.get("task_name") or traj.get("task_type") or task_type)
        except Exception:
            goal = task_type
        items.append({
            "game_id": str(game_dir),
            "split": split,
            "task_type": task_type,
            "goal": goal,
            "has_game_tw": game_file.exists(),
            "fingerprint": fingerprint(str(game_dir), goal),
        })
    return items


def build_pools(data_root: str = "/data", out_dir: str = "results/native_alfworld") -> Dict[str, Any]:
    # Development: official train-like split only.
    dev = scan_split(data_root, "valid_train", limit=50)
    # Frozen test: valid_unseen instances — mark contamination for previously viewed.
    test = scan_split(data_root, "valid_unseen", limit=30)

    # Contaminated: games seen in earlier pilots (from micro pilot logs if present).
    contaminated = []
    for cand in (
        Path("results/native_alfworld/micro_pilot/deepseek_micro_evolution.json"),
        Path(out_dir) / "micro_pilot" / "deepseek_micro_evolution.json",
    ):
        if cand.exists():
            try:
                d = json.loads(cand.read_text(encoding="utf-8"))
                contaminated = list({e.get("game_id") for e in d.get("episodes", []) if e.get("game_id")})
            except Exception:
                pass

    dev_doc = {
        "role": "development_task_pool",
        "split": "valid_train",
        "n": len(dev),
        "tasks": dev,
    }
    test_doc = {
        "role": "frozen_final_test_manifest",
        "split": "valid_unseen",
        "n": len(test),
        "tasks": test,
        "contaminated_game_ids": contaminated,
        "note": "Do not tune methods on these instances.",
    }
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "development_task_pool.json").write_text(
        json.dumps(dev_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out / "frozen_final_test_manifest.json").write_text(
        json.dumps(test_doc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"dev_n": len(dev), "test_n": len(test), "contaminated": contaminated}


if __name__ == "__main__":
    root = os.environ.get("ALFWORLD_DATA", "/data")
    print(json.dumps(build_pools(root), indent=2))
