"""Interactive LLM agent for native TextWorld loop (Stage C).

observation + genome behavior → LLM decision → admissible action → env.step
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.agent.genome import AgentGenome
from src.runtime.behavioral_agent import ALLOW_TOOLS, BudgetMeter, MemoryStore
from src.tools.registry import ToolRegistry, default_registry


class InteractiveAgent:
    """Genome-aware policy for native env stepping."""

    def __init__(
        self,
        genome: AgentGenome,
        llm_generate: Callable[[str], str],
        *,
        tools: Optional[ToolRegistry] = None,
        horizon: int = 30,
    ) -> None:
        self.genome = genome
        self.llm_generate = llm_generate
        self.tools = tools or default_registry()
        self.memory = MemoryStore(strategy=genome.memory_strategy)
        self.budget = BudgetMeter.from_reasoning_budget(genome.reasoning_budget, horizon=horizon)
        self.allow = ALLOW_TOOLS.get(genome.tool_policy, frozenset())
        self.reflection_count = 0
        self.last_fail = False

    def _plan_prefix(self, goal: str) -> List[str]:
        g = self.genome
        if g.planner_strategy in ("direct", "cot"):
            return []
        if g.planner_strategy == "plan_and_solve":
            return [f"PLAN decompose {goal[:40]}"]
        return [f"PLAN {g.planner_strategy} {goal[:40]}"]

    def select_action(self, observation: str, admissible: Sequence[str], goal: str = "") -> str:
        if not self.budget.can_step():
            return "look"
        mem = self.memory.as_context()
        self.memory.write(f"obs:{observation[:80]}")
        prompt_lines = [
            f"Goal: {goal}",
            f"Planner: {self.genome.planner_strategy}",
            f"Memory: {self.genome.memory_strategy}",
            f"Reflection: {self.genome.reflection_strategy}",
            f"Tool policy: {self.genome.tool_policy}",
        ] + self._plan_prefix(goal)
        if mem:
            prompt_lines.append("History:\n" + mem)
        prompt_lines.append("Observation:\n" + observation[:600])
        prompt_lines.append("Admissible commands:")
        for a in list(admissible)[:25]:
            prompt_lines.append(f"- {a}")
        prompt_lines.append("Choose ONE command. Reply with the command only.")
        text = self.llm_generate("\n".join(prompt_lines))
        self.budget.charge(steps=1, tokens=max(8, len(text) // 4))

        action = self._parse_action(text, admissible)
        # Reflection: if parse failed and reflection enabled, retry once with hint.
        if action is None and self.genome.reflection_strategy != "none":
            self.reflection_count += 1
            self.last_fail = True
            retry_prompt = (
                "\n".join(prompt_lines)
                + f"\nPrevious reply failed to match a command. "
                f"Previous: {text[:120]}\nReply with exactly one admissible command."
            )
            text2 = self.llm_generate(retry_prompt)
            self.budget.charge(steps=1, tokens=max(8, len(text2) // 4))
            action = self._parse_action(text2, admissible)
        if action is None:
            action = list(admissible)[0] if admissible else "look"
        return action

    def _parse_action(self, text: str, admissible: Sequence[str]) -> Optional[str]:
        t = (text or "").strip().strip('"').strip("'")
        if not t:
            return None
        # exact
        for a in admissible:
            if t == a:
                return a
        # first line match
        first = t.splitlines()[0].strip()
        for a in admissible:
            if first == a:
                return a
        # substring
        for a in admissible:
            if a.lower() in t.lower():
                return a
        return None

    def policy(self) -> Callable[[str, Sequence[str]], str]:
        def _p(obs: str, adm: Sequence[str]) -> str:
            return self.select_action(obs, adm, goal="")

        return _p
