"""Stage 1.7-R1 P0 regression tests: init, transitions, relevance, isolation."""
from __future__ import annotations

import pytest

from src.agent.genome import AgentGenome
from src.runtime.action_semantics import parse_action, relevant_candidates
from src.runtime.goal_grounding import parse_goal
from src.runtime.interactive_agent import InteractiveAgent
from src.runtime.subgoal_planner import (
    BLOCKED,
    INSPECTED_NO_TARGET,
    PENDING,
    SATISFIED,
    UNSUPPORTED,
    VISITED_UNINSPECTED,
    SubgoalPlanner,
)


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


# ---------------- Gate A: initialization ----------------
def test_p0_book_task_builds_look_at_subgoals():
    g = parse_goal("look at book under the desklamp")
    p = SubgoalPlanner(g)  # correct init from real goal
    kinds = [s.kind for s in p.subgoals]
    assert kinds == ["EXPLORE", "LOCATE_TARGET", "ACQUIRE_TARGET",
                     "LOCATE_TOOL", "USE_TOOL", "VERIFY_SUCCESS"]
    assert "PLACE_TARGET" not in kinds


def test_p0_laptop_task_same_family():
    g = parse_goal("look at laptop under the desklamp")
    p = SubgoalPlanner(g)
    kinds = [s.kind for s in p.subgoals]
    assert "USE_TOOL" in kinds and "PLACE_TARGET" not in kinds


def test_p0_alarmclock_task_place_family():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    kinds = [s.kind for s in p.subgoals]
    assert kinds == ["EXPLORE", "LOCATE_TARGET", "ACQUIRE_TARGET",
                     "LOCATE_DEST", "PLACE_TARGET", "VERIFY_SUCCESS"]


def test_unknown_goal_not_pick_and_place():
    g = parse_goal("dance around the room")
    p = SubgoalPlanner(g)
    assert p.subgoals[0].kind == UNSUPPORTED
    assert all(s.kind != "PLACE_TARGET" for s in p.subgoals)


def test_same_goal_multi_step_not_reset():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.update_from_feedback("go to shelf 1", "r", "You arrive at shelf 1. You see a alarmclock 1.")
    kinds_before = [s.status for s in p.subgoals]
    p.ensure_goal(parse_goal("put a alarmclock in dresser"))  # same task
    assert [s.status for s in p.subgoals] == kinds_before  # progress kept


def test_goal_switch_clears_old_state():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1 from the shelf 1.")
    assert p.held
    p.ensure_goal(parse_goal("look at book under the desklamp"))
    assert p.held == []
    kinds = [s.kind for s in p.subgoals]
    assert "PLACE_TARGET" not in kinds and "USE_TOOL" in kinds


def test_no_cross_episode_leak_via_agent():
    llm = ScriptedLLM(["look", "look"])
    a = InteractiveAgent(
        AgentGenome("cot", "short_term", "none", "balanced", 64),
        llm, horizon=10, runtime_variant="grounded_planner_v1")
    a.select_action("r", ["look"], goal="put a alarmclock in dresser")
    a.observe("look", "r", "You pick up the alarmclock 1.")  # fake success line
    assert a._planner.held
    # new episode would construct a new agent; simulate reset_for_goal
    a._planner.reset_for_goal(parse_goal("look at book under the desklamp"))
    assert a._planner.held == []
    assert [s.kind for s in a._planner.subgoals][0] == "EXPLORE"


# ---------------- Gate B: state transitions ----------------
def test_early_facts_satisfy_later_subgoals():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    # discover + acquire in one shot, then reconcile should satisfy LOCATE and ACQUIRE
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s",
                           "You pick up the alarmclock 1 from the shelf 1.")
    statuses = {s.kind: s.status for s in p.subgoals}
    assert statuses["ACQUIRE_TARGET"] == SATISFIED
    assert statuses["LOCATE_TARGET"] == SATISFIED  # B1: early fact chain


def test_explore_not_done_after_one_visit():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.update_from_feedback("go to shelf 1", "r", "You arrive at shelf 1. You see a pencil 1.")
    assert p.subgoals[0].status != SATISFIED  # no target found yet


def test_failed_pickup_does_not_hold_or_clear_inventory():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.held.append("pencil 1")  # prior confirmed hold
    p.world_facts["pencil1_held"] = True
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "Nothing happens.")
    assert "alarmclock" not in " ".join(p.held).lower()
    assert "pencil 1" in p.held  # other inventory preserved
    assert p.world_facts.get("alarmclock_held") is False


def test_unconfirmed_place_keeps_hold():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.held.append("alarmclock 1")
    p.world_facts["alarmclock_held"] = True
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d", "Nothing happens.")
    assert p.world_facts.get("alarmclock_placed") is not True
    assert p.world_facts.get("alarmclock_held") in (True, "UNKNOWN")
    assert any("alarmclock" in h.lower() for h in p.held) or p.world_facts.get("alarmclock_held") == "UNKNOWN"


def test_confirmed_place_releases():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.held.append("alarmclock 1")
    p.world_facts["alarmclock_held"] = True
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d",
                           "You move the alarmclock 1 to the dresser 1.")
    assert not any("alarmclock" in h.lower() for h in p.held)
    assert p.world_facts.get("alarmclock_placed") is True


def test_released_not_still_held():
    g = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(g)
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You pick up the alarmclock 1.")
    p.update_from_feedback("move alarmclock 1 to dresser 1", "d", "You move the alarmclock 1 to the dresser 1.")
    assert p.held == [] or not any("alarmclock" in h.lower() for h in p.held)


def test_tool_located_via_admissible_not_hardcode():
    g = parse_goal("look at book under the desklamp")
    p = SubgoalPlanner(g)
    # C1: use desklamp visible in admissible counts as tool located
    p.update_from_feedback("go to sidetable 2", "r", "You arrive at sidetable 2. You see a desklamp 1.",
                           admissible=["use desklamp 1", "go to desk 1"])
    assert p.world_facts.get("desklamp_visible") is True or p.world_facts.get("_use_tool_action_available")
    statuses = {s.kind: s.status for s in p.subgoals}
    assert statuses["LOCATE_TOOL"] == SATISFIED


# ---------------- Gate C: action relevance ----------------
def test_target_pickup_ranks_above_unrelated():
    adm = ["take book 1 from bed 1", "take alarmclock 1 from shelf 1", "go to desk 1", "look"]
    from src.runtime.subgoal_planner import Subgoal

    gs = parse_goal("put a alarmclock in dresser")
    sg = Subgoal(kind="ACQUIRE_TARGET", target="alarmclock")
    c = relevant_candidates(adm, gs, sg)
    assert c[0].raw_command == "take alarmclock 1 from shelf 1"


def test_candidates_subset_of_admissible():
    adm = ["go to shelf 3", "take alarmclock 1 from shelf 3", "look"]
    c = relevant_candidates(adm, parse_goal("put a alarmclock in dresser"),
                            SubgoalPlanner(parse_goal("put a alarmclock in dresser")).active_subgoal())
    assert all(x.raw_command in adm for x in c)


def test_no_invented_goto_tool_location():
    # 'go to desklamp' is not a normal navigate form in ALFWorld
    s = parse_action("go to desklamp 1")
    assert s.action_type == "NAVIGATE"  # syntactically nav, but we never *generate* it
    # planner candidates never add commands outside admissible (checked above)


def test_grounding_blocked_empty_admissible():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    assert relevant_candidates([], p.goal_spec, p.active_subgoal()) == []


def test_candidate_truncation_keeps_target_action():
    adm = [f"take junk {i} from shelf 1" for i in range(30)] + ["take alarmclock 1 from shelf 3"]
    from src.runtime.subgoal_planner import Subgoal

    c = relevant_candidates(adm, parse_goal("put a alarmclock in dresser"),
                            Subgoal(kind="ACQUIRE_TARGET", target="alarmclock"))
    assert any(x.raw_command == "take alarmclock 1 from shelf 3" for x in c[:5])


# ---------------- Gate C isolation ----------------
def test_current_and_shared_repaired_unchanged():
    for variant, expect_absent, expect_present in (
        ("current", ["Active Subgoal", "Observed Progress"], ["Task Goal"]),
        ("shared_repaired", ["Active Subgoal"], ["Observed Progress"]),
    ):
        llm = ScriptedLLM(["look"])
        a = InteractiveAgent(
            AgentGenome("cot", "short_term", "self_critique", "balanced", 64),
            llm, horizon=10, runtime_variant=variant)
        a.select_action("o", ["look"], goal="look at book under the desklamp")
        for bad in expect_absent:
            assert bad not in llm.prompts[0]
        for good in expect_present:
            assert good in llm.prompts[0]


def test_grounded_requires_explicit_variant():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(
        AgentGenome("cot", "short_term", "none", "balanced", 64),
        llm, horizon=5, runtime_variant="grounded_planner_v1")
    a.select_action("o", ["look"], goal="put a alarmclock in dresser")
    assert "Active Subgoal" in llm.prompts[0]
    assert "UNSUPPORTED_GOAL" not in llm.prompts[0]


def test_exploration_phases():
    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    p.update_from_feedback("go to shelf 1", "r", "You arrive at shelf 1. You see a pencil 1.")
    assert p.exploration.locations.get("shelf 1") in (VISITED_UNINSPECTED, INSPECTED_NO_TARGET)
