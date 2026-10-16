"""Stage 1.8 offline gate tests: A1 placement, A2 admissible sync, A3 reopen."""
from __future__ import annotations

import pytest

from src.agent.genome import AgentGenome
from src.runtime.goal_grounding import parse_goal
from src.runtime.interactive_agent import InteractiveAgent
from src.runtime.subgoal_planner import PENDING, SATISFIED, UNSUPPORTED, SubgoalPlanner


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.i = 0

    def __call__(self, prompt):
        self.prompts.append(prompt)
        r = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return r


def g1():
    return AgentGenome("cot", "short_term", "self_critique", "balanced", 64)


# ---------------- A1: placement correctness ----------------
def test_wrong_object_correct_destination():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.held.append("pen 1")
    p.world_facts["pen1_held"] = True
    p.update_from_feedback("move pen 1 to dresser 1", "d",
                           "You move the pen 1 to the dresser 1.")
    assert p.world_facts.get("goal_placement_satisfied") is not True
    assert p.world_facts.get("alarmclock_placed") is not True


def test_correct_object_wrong_destination():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.held.append("alarmclock 1")
    p.world_facts["alarmclock_held"] = True
    p.update_from_feedback("move alarmclock 1 to bed 1", "b",
                           "You move the alarmclock 1 to the bed 1.")
    assert p.world_facts.get("goal_placement_satisfied") is not True
    assert p.world_facts.get("alarmclock_placed") is not True
    assert p.world_facts.get("object_released") is True
    assert not any("alarmclock" in h.lower() for h in p.held)


def test_correct_object_correct_destination():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.held.append("alarmclock 1")
    p.world_facts["alarmclock_held"] = True
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d",
                           "You move the alarmclock 1 to the dresser 1.")
    assert p.world_facts.get("goal_placement_satisfied") is True
    assert p.world_facts.get("alarmclock_placed") is True


def test_failed_place_preserves_hold():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.held.append("alarmclock 1")
    p.world_facts["alarmclock_held"] = True
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d", "Nothing happens.")
    assert any("alarmclock" in h.lower() for h in p.held) or p.world_facts.get("alarmclock_held") in (True, "UNKNOWN")
    assert p.world_facts.get("goal_placement_satisfied") is not True


def test_successful_wrong_place_reopens_acquire():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    # acquire first
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1 from the shelf 1.")
    st = {s.kind: s.status for s in p.subgoals}
    assert st["ACQUIRE_TARGET"] == SATISFIED
    # wrong place
    p.update_from_feedback("move alarmclock 1 to bed 1", "b", "You move the alarmclock 1 to the bed 1.")
    st = {s.kind: s.status for s in p.subgoals}
    assert st["ACQUIRE_TARGET"] != SATISFIED  # reopened
    assert st["PLACE_TARGET"] != SATISFIED


# ---------------- A2: admissible synchronization ----------------
def test_new_use_action_seen_after_navigation():
    llm = ScriptedLLM(["go to sidetable 2", "use desklamp 1"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="grounded_planner_v1")
    a.select_action("room", ["go to sidetable 2", "go to desk 1"],
                    goal="look at book under the desklamp")
    a.observe("go to sidetable 2", "room", "You see a desklamp 1.",
              admissible_after=["use desklamp 1", "go to desk 1"])
    # planner should know use is available NOW
    assert a._planner.world_facts.get("_use_tool_action_available") is True
    assert a._planner.world_facts.get("desklamp_visible") is True


def test_stale_use_not_available_after_leave():
    llm = ScriptedLLM(["go to sidetable 2", "go to desk 1"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="grounded_planner_v1")
    a.select_action("room", ["go to sidetable 2"], goal="look at book under the desklamp")
    a.observe("go to sidetable 2", "r", "You see a desklamp 1.",
              admissible_after=["use desklamp 1"])
    assert a._planner.world_facts.get("_use_tool_action_available") is True
    a.observe("go to desk 1", "s", "You arrive at desk 1.",
              admissible_after=["go to shelf 1", "look"])  # no use here
    assert a._planner.world_facts.get("_use_tool_action_available") is False


def test_current_runtime_prompt_unchanged_with_admissible_after():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(g1(), llm, horizon=5, runtime_variant="current")
    a.select_action("o", ["look"], goal="g")
    a.observe("look", "o", "o2", admissible_after=["look"])
    assert "Active Subgoal" not in llm.prompts[0]
    assert len(llm.prompts) == 1  # no extra LLM calls


def test_observation_logs_can_distinguish_before_after():
    # EpisodeRunner trajectory stores admissible_commands (before); planner
    # consumes after — covered by agent.observe signature
    import inspect

    sig = inspect.signature(InteractiveAgent.observe)
    assert "admissible_after" in sig.parameters


# ---------------- A3: reopen subgoals ----------------
def test_acquire_then_release_reopens_acquire():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1.")
    assert any(s.kind == "ACQUIRE_TARGET" and s.status == SATISFIED for s in p.subgoals)
    p.update_from_feedback("move alarmclock 1 to bed 1", "b", "You move the alarmclock 1 to the bed 1.")
    acq = next(s for s in p.subgoals if s.kind == "ACQUIRE_TARGET")
    assert acq.status == PENDING


def test_acquire_then_wrong_place():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1.")
    p.update_from_feedback("move alarmclock 1 to shelf 2", "x", "You move the alarmclock 1 to the shelf 2.")
    assert p.world_facts.get("goal_placement_satisfied") is not True
    assert next(s for s in p.subgoals if s.kind == "ACQUIRE_TARGET").status != SATISFIED


def test_correct_place_then_native_won():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1.")
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d", "You move the alarmclock 1 to the dresser 1.")
    p.mark_native_won(True)
    assert all(s.status == SATISFIED for s in p.subgoals)


def test_unknown_not_treated_as_true():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.world_facts["alarmclock_held"] = "UNKNOWN"
    p._reconcile()
    assert next(s for s in p.subgoals if s.kind == "ACQUIRE_TARGET").status != SATISFIED


def test_unsupported_goal_still_unsupported():
    p = SubgoalPlanner(parse_goal("fly to the moon"))
    assert p.subgoals[0].kind == UNSUPPORTED
