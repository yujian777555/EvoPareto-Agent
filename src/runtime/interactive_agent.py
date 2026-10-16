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
    # --- observational only (Stage 1 DecisionLog). Do not affect decisions. ---
    step_index: int = -1
    reflection_trigger: str = ""  # "" | parse_failure
    llm_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    estimated_cost_usd: float = 0.0


class InteractiveAgent:
    def __init__(
        self,
        genome: AgentGenome,
        llm_generate: Callable[[str], str],
        *,
        horizon: int = 20,
        runtime_variant: str = "current",
    ) -> None:
        self.genome = genome
        self.llm_generate = llm_generate
        self.memory = MemoryStore(strategy=genome.memory_strategy)
        self.budget = BudgetMeter.from_reasoning_budget(genome.reasoning_budget, horizon=horizon)
        self.allow = ALLOW_TOOLS.get(genome.tool_policy, frozenset())
        self.reflection_count = 0
        self.decision_logs: List[DecisionLog] = []
        self.runtime_variant = runtime_variant  # "current" | "shared_repaired" | "grounded_planner_v1"
        self._recorder = None
        self._stagnation = None
        self._goal_state = {}
        self._task_type = ""
        self._last_goal = ""
        self._last_observation = ""
        self._goal_spec = None
        self._planner = None
        if runtime_variant in ("shared_repaired", "grounded_planner_v1"):
            from src.diagnostics.shared_repair import (
                ActionObservationRecorder,
                StagnationDetector,
            )

            self._recorder = ActionObservationRecorder()
            self._stagnation = StagnationDetector()
            self._goal_state = {}
        if runtime_variant == "grounded_planner_v1":
            from src.runtime.goal_grounding import parse_goal
            from src.runtime.subgoal_planner import SubgoalPlanner

            self._goal_spec = parse_goal("")
            self._planner = SubgoalPlanner(self._goal_spec)
        self.repaired_prompt_blocks: List[str] = []

    def observe(self, action: str, observation_before: str, observation_after: str, *,
                parse_ok: bool = True, used_fallback: bool = False) -> None:
        """Record environment feedback after a step (shared_repaired / grounded)."""
        if self._recorder is None:
            return
        from src.diagnostics.shared_repair import StepRecord, goal_state_tracker

        step_index = len(self._recorder.events) + 1
        self._recorder.record(
            StepRecord(
                step_index=step_index,
                observation_before=observation_before,
                action=action,
                observation_after=observation_after,
                parse_ok=parse_ok,
                used_fallback=used_fallback,
            )
        )
        self._goal_state = goal_state_tracker(
            self._task_type or "", self._recorder, self._last_goal or ""
        )
        self._last_observation = observation_after
        if self._planner is not None:
            self._planner.update_from_feedback(
                action, observation_before, observation_after,
                admissible=getattr(self, "_last_admissible", None),
            )

    def select_action(
        self,
        observation: str,
        admissible: Sequence[str],
        goal: str = "",
    ) -> str:
        if not goal:
            goal = "(no task goal provided)"
        self._last_goal = goal
        # A2: derive task_type from public goal text (no hidden state)
        if not self._task_type and goal and "no task goal" not in goal:
            try:
                from src.runtime.goal_grounding import parse_goal

                self._task_type = parse_goal(goal).task_family or ""
            except Exception:
                self._task_type = ""
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
        # --- shared_repaired / grounded: verified progress block ---
        self._last_admissible = list(admissible)
        if self.runtime_variant == "shared_repaired" and self._recorder is not None:
            from src.diagnostics.shared_repair import format_repaired_prompt_block

            stag = self._stagnation.check(self._recorder) if self._stagnation else {}
            gs = dict(self._goal_state or {})
            # A4: none→0, short_term→1, episodic/semantic/hybrid→3 (not None=ALL)
            if self.genome.memory_strategy == "none":
                mem_k = 0
            elif self.genome.memory_strategy == "short_term":
                mem_k = 1
            else:
                mem_k = 3
            gs["memory_strategy"] = self.genome.memory_strategy
            block = format_repaired_prompt_block(
                goal, self._recorder, stag, gs, memory_k=mem_k
            )
            prompt_lines.append(block)
            self.repaired_prompt_blocks.append(block)
        elif self.runtime_variant == "grounded_planner_v1" and self._planner is not None:
            from src.runtime.goal_grounding import parse_goal

            if self._goal_spec is None or self._goal_spec.raw_goal != goal:
                self._goal_spec = parse_goal(goal)
                self._planner.goal_spec = self._goal_spec
            # task_family from GoalSpec feeds goal-state tracker
            self._task_type = self._goal_spec.task_family or self._task_type
            block = self._planner.prompt_block(admissible)
            prompt_lines.append(block)
            self.repaired_prompt_blocks.append(block)
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
            log.reflection_trigger = "parse_failure"
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
