"""Agent genome: DNA of a multi-objective agent configuration.

Phase 0 focuses on a discrete/categorical configuration vector that can be
mutated by agent-specific operators and evaluated by a toy objective model.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Mapping, Tuple


# Strategy option sets. Keep them small and closed so mutation is well-defined
# without touching a real LLM in Phase 0.
PLANNER_STRATEGIES: Tuple[str, ...] = (
    "direct",
    "cot",
    "plan_and_solve",
    "tree_search",
    "reflexion",
)

MEMORY_STRATEGIES: Tuple[str, ...] = (
    "none",
    "short_term",
    "episodic",
    "semantic",
    "hybrid",
)

REFLECTION_STRATEGIES: Tuple[str, ...] = (
    "none",
    "self_critique",
    "pairwise",
    "critic_model",
    "iterative",
)

TOOL_POLICIES: Tuple[str, ...] = (
    "conservative",
    "balanced",
    "aggressive",
    "tool_first",
    "no_tools",
)

# reasoning_budget is an integer in [MIN_BUDGET, MAX_BUDGET].
MIN_BUDGET = 8
MAX_BUDGET = 128


@dataclass(frozen=True)
class AgentGenome:
    """Serializable, comparable, mutable (via replace) agent configuration.

    Attributes
    ----------
    planner_strategy:
        High-level planning mode of the agent.
    memory_strategy:
        External / internal memory policy.
    reflection_strategy:
        Self-improvement / critique policy.
    tool_policy:
        How aggressively tools are used.
    reasoning_budget:
        Discrete budget for reasoning steps / tokens.
    """

    planner_strategy: str
    memory_strategy: str
    reflection_strategy: str
    tool_policy: str
    reasoning_budget: int

    def __post_init__(self) -> None:
        self._validate()

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def _validate(self) -> None:
        if self.planner_strategy not in PLANNER_STRATEGIES:
            raise ValueError(
                f"planner_strategy must be one of {PLANNER_STRATEGIES}, "
                f"got {self.planner_strategy!r}"
            )
        if self.memory_strategy not in MEMORY_STRATEGIES:
            raise ValueError(
                f"memory_strategy must be one of {MEMORY_STRATEGIES}, "
                f"got {self.memory_strategy!r}"
            )
        if self.reflection_strategy not in REFLECTION_STRATEGIES:
            raise ValueError(
                f"reflection_strategy must be one of {REFLECTION_STRATEGIES}, "
                f"got {self.reflection_strategy!r}"
            )
        if self.tool_policy not in TOOL_POLICIES:
            raise ValueError(
                f"tool_policy must be one of {TOOL_POLICIES}, "
                f"got {self.tool_policy!r}"
            )
        if not isinstance(self.reasoning_budget, int):
            raise TypeError("reasoning_budget must be int")
        if not (MIN_BUDGET <= self.reasoning_budget <= MAX_BUDGET):
            raise ValueError(
                f"reasoning_budget must be in [{MIN_BUDGET}, {MAX_BUDGET}], "
                f"got {self.reasoning_budget}"
            )

    # ------------------------------------------------------------------ #
    # Serialization
    # ------------------------------------------------------------------ #
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AgentGenome":
        required = (
            "planner_strategy",
            "memory_strategy",
            "reflection_strategy",
            "tool_policy",
            "reasoning_budget",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise ValueError(f"AgentGenome.from_dict missing keys: {missing}")
        return cls(
            planner_strategy=str(data["planner_strategy"]),
            memory_strategy=str(data["memory_strategy"]),
            reflection_strategy=str(data["reflection_strategy"]),
            tool_policy=str(data["tool_policy"]),
            reasoning_budget=int(data["reasoning_budget"]),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, payload: str) -> "AgentGenome":
        return cls.from_dict(json.loads(payload))

    def clone(self) -> "AgentGenome":
        return copy.deepcopy(self)

    # ------------------------------------------------------------------ #
    # Comparison / hashing
    # ------------------------------------------------------------------ #
    def key(self) -> Tuple[str, str, str, str, int]:
        """Stable identity key used for deduplication and sorting."""
        return (
            self.planner_strategy,
            self.memory_strategy,
            self.reflection_strategy,
            self.tool_policy,
            self.reasoning_budget,
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, AgentGenome):
            return NotImplemented
        return self.key() < other.key()

    def distance(self, other: "AgentGenome") -> int:
        """Hamming-like distance over categorical fields + budget steps.

        Used by operators / novelty metrics; not required by NSGA-III itself.
        """
        if not isinstance(other, AgentGenome):
            raise TypeError("distance requires another AgentGenome")
        d = 0
        d += int(self.planner_strategy != other.planner_strategy)
        d += int(self.memory_strategy != other.memory_strategy)
        d += int(self.reflection_strategy != other.reflection_strategy)
        d += int(self.tool_policy != other.tool_policy)
        # Budget distance in units of 8 to keep the scale comparable.
        d += abs(self.reasoning_budget - other.reasoning_budget) // 8
        return d

    # ------------------------------------------------------------------ #
    # Mutation support (pure / immutable)
    # ------------------------------------------------------------------ #
    def replace(self, **changes: Any) -> "AgentGenome":
        """Return a new genome with the given fields replaced."""
        data = self.to_dict()
        data.update(changes)
        return AgentGenome.from_dict(data)

    @staticmethod
    def random(rng) -> "AgentGenome":
        """Sample a random genome using a `random.Random` instance."""
        return AgentGenome(
            planner_strategy=rng.choice(PLANNER_STRATEGIES),
            memory_strategy=rng.choice(MEMORY_STRATEGIES),
            reflection_strategy=rng.choice(REFLECTION_STRATEGIES),
            tool_policy=rng.choice(TOOL_POLICIES),
            reasoning_budget=rng.randrange(MIN_BUDGET, MAX_BUDGET + 1, 8),
        )

    def fields(self) -> Iterable[str]:
        return (
            "planner_strategy",
            "memory_strategy",
            "reflection_strategy",
            "tool_policy",
            "reasoning_budget",
        )
