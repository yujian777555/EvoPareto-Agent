"""ALFWorld split integrity (Phase5-R3-R4-R2 Task A)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# Explicit mapping: user split -> (train_eval, relative data dir)
SPLIT_MAP: Dict[str, Tuple[str, str]] = {
    "valid_train": ("train", "valid_train"),
    "train": ("train", "valid_train"),
    "valid_seen": ("eval_in_distribution", "valid_seen"),
    "valid_unseen": ("eval_out_of_distribution", "valid_unseen"),
}

ALLOWED_SPLITS = tuple(sorted(SPLIT_MAP))


class SplitIntegrityError(RuntimeError):
    """Raised when actual game does not belong to the requested split."""


def resolve_split(user_split: str) -> Tuple[str, str]:
    if user_split not in SPLIT_MAP:
        raise SplitIntegrityError(
            f"unsupported split {user_split!r}; allowed={ALLOWED_SPLITS}"
        )
    return SPLIT_MAP[user_split]


def data_dir_for(user_split: str, data_root: str) -> str:
    _, rel = resolve_split(user_split)
    return str(Path(data_root) / "json_2.1.1" / rel)


def validate_game_in_split(game_id: str, user_split: str) -> str:
    """Return normalized game_id if it lies in the requested split."""
    _, rel = resolve_split(user_split)
    norm = os.path.normpath(str(game_id)).replace("\\", "/")
    marker = f"/json_2.1.1/{rel}/"
    if marker not in norm + "/" and marker not in ("/" + norm):
        # also accept relative form
        if f"json_2.1.1/{rel}/" not in norm:
            raise SplitIntegrityError(
                f"game {norm!r} not in requested split {user_split!r} (expect {rel})"
            )
    return norm


def normalize_game_id(game_id: str) -> str:
    return os.path.normpath(str(game_id)).replace("\\", "/")


def manifest_overlap(dev_fps, test_fps) -> list:
    return sorted(set(dev_fps) & set(test_fps))
