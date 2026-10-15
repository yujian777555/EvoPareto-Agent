"""Behavioral agent runtime (Phase5-R3-R1).

Maps genome fields to *actual execution behavior*, not just prompt text:

- memory_strategy  → MemoryStore read/write rules
- reflection_strategy → retry/refine on failure
- tool_policy      → tool allowlist enforcement
- reasoning_budget → hard call/token budget
- planner_strategy → plan / execute structure (multi-step)

`PROMPT_ONLY` fields (if any remain) are labeled explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.agent.genome import AgentGenome
from src.tools.registry import ToolRegistry, default_registry


@dataclass
class MemoryStore:
    """Simple episodic store gated by memory_strategy."""

    strategy: str
    items: List[str] = field(default_factory=list)
    reads: int = 0
    writes: int = 0

    def enabled(self) -> bool:
        return self.strategy != "none"

    def write(self, item: str) -> bool:
        if not self.enabled():
            return False
        self.items.append(str(item))
        self.writes += 1
        return True

    def read(self, k: int = 3) -> List[str]:
        if not self.enabled():
            return []
        self.reads += 1
        if self.strategy == "short_term":
            return self.items[-1:]
        return self.items[-k:]

    def as_context(self) -> str:
        if not self.enabled():
            return ""
        return "\n".join(self.read(3))


ALLOW_TOOLS = {
    "no_tools": frozenset(),
    "conservative": frozenset({"calculator", "file_read"}),
    "balanced": frozenset({"calculator", "search", "file_read", "file_list"}),
    "aggressive": frozenset({"calculator", "search", "file_read", "file_write", "file_list"}),
    "tool_first": frozenset({"calculator", "search", "file_read", "file_write", "file_list"}),
}


@dataclass
class BudgetMeter:
    max_steps: int
    max_tokens: int
    used_steps: int = 0
    used_tokens: int = 0

    @classmethod
    def from_reasoning_budget(cls, reasoning_budget: int, *, horizon: int = 8) -> "BudgetMeter":
        steps = max(1, int(round(horizon * (0.5 + reasoning_budget / 128.0))))
        tokens = max(64, reasoning_budget * 12)
        return cls(max_steps=steps, max_tokens=tokens)

    def can_step(self) -> bool:
        return self.used_steps < self.max_steps and self.used_tokens < self.max_tokens

    def charge(self, steps: int = 1, tokens: int = 0) -> None:
        self.used_steps += int(steps)
        self.used_tokens += int(tokens)


class BehavioralAgent:
    """Executes a genome with real behavioral constraints."""

    def __init__(self, genome: AgentGenome, *, tools: Optional[ToolRegistry] = None,
                 horizon: int = 8) -> None:
        self.genome = genome
        self.tools = tools or default_registry()
        self.memory = MemoryStore(strategy=genome.memory_strategy)
        self.budget = BudgetMeter.from_reasoning_budget(genome.reasoning_budget, horizon=horizon)
        self.allow = ALLOW_TOOLS.get(genome.tool_policy, frozenset({"calculator"}))
        self.trajectory: List[Dict[str, Any]] = []
        self.reflection_events: List[Dict[str, Any]] = []

    def _plan(self, goal: str) -> List[str]:
        g = self.genome
        if g.planner_strategy in ("direct", "cot"):
            return [f"act:{goal[:40]}"]
        if g.planner_strategy == "plan_and_solve":
            return [f"decompose:{goal[:30]}", f"solve:{goal[:30]}"]
        if g.planner_strategy == "tree_search":
            return [f"branch:{goal[:20]}", f"select:{goal[:20]}", f"exec:{goal[:20]}"]
        return [f"plan:{goal[:30]}", f"exec:{goal[:30]}", f"check:{goal[:20]}"]

    def _may_use(self, tool_name: str) -> bool:
        return tool_name in self.allow

    def invoke_tool(self, name: str, **kwargs: Any):
        """Enforce tool_policy allowlist + budget."""
        if not self._may_use(name):
            self.trajectory.append({"action": "tool_denied", "tool": name, "policy": self.genome.tool_policy})
            return None
        if not self.budget.can_step():
            self.trajectory.append({"action": "budget_exhausted", "tool": name})
            return None
        res = self.tools.invoke(name, **kwargs)
        self.budget.charge(steps=1, tokens=8)
        self.trajectory.append({"action": "tool", "tool": name, "ok": res.ok})
        return res

    def run_task(self, goal: str, *, required_tool: str = "", seed: int = 0) -> Dict[str, Any]:
        """Multi-step behavioral execution. Returns verifiable run log."""
        steps = self._plan(goal)
        success = False
        self.memory.write(f"goal:{goal}")
        for step in steps:
            if not self.budget.can_step():
                break
            self.trajectory.append({"action": step})
            self.budget.charge(steps=1, tokens=4)
            # Tool if required and allowed.
            if required_tool and self._may_use(required_tool):
                self.invoke_tool(required_tool, query=goal, expression="1+1", path="notes.txt", content=goal[:20])
            elif required_tool and not self._may_use(required_tool):
                self.trajectory.append({"action": "required_tool_blocked", "tool": required_tool})
            self.memory.write(step)

        # Reflection: retry once when enabled and not successful yet.
        success = self._evaluate_outcome(goal, required_tool)
        if not success and self.genome.reflection_strategy not in ("none",):
            self.reflection_events.append({"strategy": self.genome.reflection_strategy, "goal": goal})
            self.trajectory.append({"action": "reflect", "strategy": self.genome.reflection_strategy})
            if self.budget.can_step():
                self.budget.charge(steps=1, tokens=6)
                if required_tool and self._may_use(required_tool):
                    self.invoke_tool(required_tool, query=goal, expression="1+1", path="notes.txt")
                success = self._evaluate_outcome(goal, required_tool)

        return {
            "success": success,
            "steps_used": self.budget.used_steps,
            "tokens_used": self.budget.used_tokens,
            "max_steps": self.budget.max_steps,
            "max_tokens": self.budget.max_tokens,
            "memory_reads": self.memory.reads,
            "memory_writes": self.memory.writes,
            "memory_strategy": self.genome.memory_strategy,
            "tool_policy": self.genome.tool_policy,
            "planner_strategy": self.genome.planner_strategy,
            "reflection_events": len(self.reflection_events),
            "allowed_tools": sorted(self.allow),
            "trajectory": list(self.trajectory),
        }

    def _evaluate_outcome(self, goal: str, required_tool: str) -> bool:
        """Behavioral (not LLM) outcome for consistency tests.

        A task is successful only if required tool was executed successfully
        (when required) and at least one planned step completed within budget.
        """
        tool_ok = True
        if required_tool:
            tool_ok = any(
                t.get("action") == "tool" and t.get("ok") and t.get("tool") == required_tool
                for t in self.trajectory
            )
        acted = any(str(t.get("action", "")).startswith(("act:", "decompose:", "solve:", "branch:", "plan:", "exec:")) for t in self.trajectory)
        return bool(tool_ok and acted and self.budget.used_steps <= self.budget.max_steps)


# Explicit PROMPT_ONLY markers (if any genome knobs still only affect prompts).
PROMPT_ONLY_FIELDS = (
    # reasoning_budget also gates BudgetMeter — not prompt-only.
    # planner_strategy changes step structure — not prompt-only.
    # All five fields have behavioral effects in BehavioralAgent.
)


def behavior_report(genome: AgentGenome, goal: str, required_tool: str = "") -> Dict[str, Any]:
    agent = BehavioralAgent(genome)
    return agent.run_task(goal, required_tool=required_tool)
