"""Interactive LLM agent for native TextWorld (Phase5-R3-R3).

Fixes vs R3-R2:
- goal is mandatory and threaded through every decision
- budget exhausted => stop (no infinite `look`)
- parse failure is logged; fallback is explicit and uniform
- reflection changes the next decision context (not just a label)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from src.agent.genome import AgentGenome
from src.runtime.behavioral_agent import ALLOW_TOOLS, BudgetMeter, MemoryStore


class BudgetExhaustedStop(Exception):
    pass


@dataclass
class DecisionLog:
    goal: str
    observation_preview: str
    raw_response: str = ""
    parse_ok: bool = False
    parse_failure_reason: str = ""
    reflected: bool = False
    reflection_raw: str = ""
    chosen_action: str = ""
    used_fallback: bool = False


class InteractiveAgent:
    def __init__(
        self,
        genome: AgentGenome,
        llm_generate: Callable[[str], str],
        *,
        horizon: int = 20,
    ) -> None:
        self.genome = genome
        self.llm_generate = llm_generate
        self.memory = MemoryStore(strategy=genome.memory_strategy)
        self.budget = BudgetMeter.from_reasoning_budget(genome.reasoning_budget, horizon=horizon)
        self.allow = ALLOW_TOOLS.get(genome.tool_policy, frozenset())
        self.reflection_count = 0
        self.decision_logs: List[DecisionLog] = []

    def select_action(
        self,
        observation: str,
        admissible: Sequence[str],
        goal: str = "",
    ) -> str:
        if not goal:
            goal = "(no task goal provided)"
        if not self.budget.can_step():
            # Caller must stop the episode; return sentinel.
            raise BudgetExhaustedStop("budget_exhausted")

        # Memory: write then read; read feeds the prompt (behavioral).
        self.memory.write(f"obs:{observation[:120]}")
        mem = self.memory.as_context()

        prompt_lines = [
            f"Task Goal: {goal}",
            f"Planner: {self.genome.planner_strategy}",
            f"Memory: {self.genome.memory_strategy}",
            f"Reflection: {self.genome.reflection_strategy}",
            f"Tool policy: {self.genome.tool_policy}",
            f"Remaining budget steps: {max(0, self.budget.max_steps - self.budget.used_steps)}",
        ]
        if self.genome.planner_strategy == "plan_and_solve":
            prompt_lines.append("Strategy: decompose goal into sub-steps then act.")
        elif self.genome.planner_strategy == "tree_search":
            prompt_lines.append("Strategy: consider alternatives, then commit one action.")
        elif self.genome.planner_strategy == "reflexion":
            prompt_lines.append("Strategy: act, then revise if observation contradicts plan.")
        if mem:
            prompt_lines.append("History:\n" + mem)
        prompt_lines.append("Observation:\n" + (observation or "")[:800])
        prompt_lines.append("Admissible commands:")
        for a in list(admissible)[:40]:
            prompt_lines.append(f"- {a}")
        prompt_lines.append("Choose ONE command that advances the task goal. Reply with the command only.")

        log = DecisionLog(goal=goal, observation_preview=(observation or "")[:120])
        text = self.llm_generate("\n".join(prompt_lines))
        self.budget.charge(steps=1, tokens=max(8, len(text) // 4))
        log.raw_response = text[:500]
        action, reason = self._parse_action(text, admissible)
        log.parse_ok = action is not None
        log.parse_failure_reason = reason

        if action is None and self.genome.reflection_strategy != "none":
            self.reflection_count += 1
            log.reflected = True
            retry = (
                "\n".join(prompt_lines)
                + f"\nPrevious reply was invalid ({reason}). "
                f"Previous: {text[:160]}\nReply with exactly one admissible command."
            )
            text2 = self.llm_generate(retry)
            self.budget.charge(steps=1, tokens=max(8, len(text2) // 4))
            log.reflection_raw = text2[:500]
            action, reason2 = self._parse_action(text2, admissible)
            log.parse_ok = action is not None
            if action is None:
                log.parse_failure_reason = reason2

        if action is None:
            # Explicit, uniform fallback (logged).
            action = list(admissible)[0] if admissible else "look"
            log.used_fallback = True

        log.chosen_action = action
        self.decision_logs.append(log)
        return action

    def _parse_action(self, text: str, admissible: Sequence[str]) -> Tuple[Optional[str], str]:
        t = (text or "").strip().strip('"').strip("'")
        if not t:
            return None, "empty_response"
        first = t.splitlines()[0].strip()
        for a in admissible:
            if first == a or t == a:
                return a, ""
        tl = t.lower()
        for a in admissible:
            if a.lower() in tl:
                return a, ""
        return None, "no_admissible_match"

    def policy(self, goal: str = "") -> Callable[[str, Sequence[str]], str]:
        def _p(obs: str, adm: Sequence[str]) -> str:
            return self.select_action(obs, adm, goal=goal)

        return _p
