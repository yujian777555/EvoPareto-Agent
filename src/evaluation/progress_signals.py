"""Progress signals + failure taxonomy (Phase5-R3-R4 Task3) — DIAGNOSTIC ONLY."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


FAILURE_REASONS = (
    "budget_exhausted",
    "max_steps",
    "stalled_no_obs_change",
    "repeated_action_loop",
    "invalid_action",
    "api_failure",
    "environment_error",
    "task_failed",
    "task_success",
)


def classify_failure(termination_reason: str, success: bool) -> str:
    if success:
        return "task_success"
    tr = (termination_reason or "").lower()
    for name in FAILURE_REASONS:
        if name in tr:
            return name
    return "task_failed"


def obs_changed(a: str, b: str) -> bool:
    return (a or "").strip() != (b or "").strip()


def count_repeated_actions(trajectory: Sequence[Dict[str, Any]]) -> int:
    rep = 0
    prev = None
    for t in trajectory:
        a = t.get("action")
        if a is not None and a == prev:
            rep += 1
        prev = a
    return rep


def progress_signals(trajectory: Sequence[Dict[str, Any]], goal: str) -> Dict[str, Any]:
    """Environment-observable progress diagnostics (not fitness)."""
    goal_l = (goal or "").lower()
    objects = set(re.findall(r"\b[a-z]{3,}\b", goal_l)) - {
        "your", "task", "put", "the", "and", "with", "into", "onto", "some", "then",
        "clean", "heat", "cool", "look", "that", "this", "from", "them",
    }
    found_obj = False
    picked = False
    opened = False
    state_changes = 0
    last = None
    for t in trajectory:
        obs = str(t.get("obs", ""))
        act = str(t.get("action", "")).lower()
        if last is not None and obs_changed(last, obs):
            state_changes += 1
        last = obs
        ol = obs.lower()
        if any(o in ol for o in objects):
            found_obj = True
        if act.startswith("take "):
            picked = True
        if act.startswith("open "):
            opened = True
    return {
        "found_goal_object": found_obj,
        "picked_something": picked,
        "opened_container": opened,
        "state_changes": state_changes,
        "repeated_actions": count_repeated_actions(trajectory),
        "n_steps": len(trajectory),
    }


def positive_control_expectation() -> Dict[str, Any]:
    """Document what a valid positive control must show (no gold leak to agents)."""
    return {
        "requires": [
            "solvable train-split game",
            "expert_or_valid_action_sequence",
            "env.won becomes True",
            "evaluator records success=True",
        ],
        "forbidden_in_agent": ["gold_action_sequence", "expert_trajectory", "hidden_solution"],
    }
