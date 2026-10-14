"""Task specification for agent evaluation (Phase 1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class TaskSpec:
    """One benchmark task an agent may attempt.

    Attributes
    ----------
    task_id:
        Stable identifier.
    goal:
        Natural-language goal (unused by mock runtime; kept for future LLMs).
    difficulty:
        In (0, 1]; higher means harder.
    required_tools:
        Tool names that help on this task (used by mock tool policy).
    domain:
        Free-form domain tag (e.g. "webshop", "alfworld").
    metadata:
        Extra payload for specialized benchmarks.
    """

    task_id: str
    goal: str
    difficulty: float = 0.5
    required_tools: Tuple[str, ...] = ()
    domain: str = "mock"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id must be non-empty")
        if not (0.0 < self.difficulty <= 1.0):
            raise ValueError(f"difficulty must be in (0, 1], got {self.difficulty}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "difficulty": float(self.difficulty),
            "required_tools": list(self.required_tools),
            "domain": self.domain,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSpec":
        return cls(
            task_id=str(data["task_id"]),
            goal=str(data.get("goal", "")),
            difficulty=float(data.get("difficulty", 0.5)),
            required_tools=tuple(data.get("required_tools", ())),
            domain=str(data.get("domain", "mock")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class TaskSuite:
    """A fixed set of tasks used for one evaluation episode."""

    name: str
    tasks: Tuple[TaskSpec, ...]

    def __post_init__(self) -> None:
        if not self.tasks:
            raise ValueError("TaskSuite requires at least one task")

    def __len__(self) -> int:
        return len(self.tasks)

    def __iter__(self):
        return iter(self.tasks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "tasks": [t.to_dict() for t in self.tasks],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "TaskSuite":
        return cls(
            name=str(data["name"]),
            tasks=tuple(TaskSpec.from_dict(t) for t in data["tasks"]),
        )
