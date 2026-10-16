"""Stage 1.7 offline tests: goal semantics, action grounding, subgoal transitions,
runtime isolation, memory window, no-oracle checks."""
from __future__ import annotations

import pytest

from src.agent.genome import AgentGenome
from src.runtime.action_semantics import parse_action, parse_admissible, relevant_candidates
from src.runtime.goal_grounding import UNKNOWN, parse_goal
from src.runtime.interactive_agent import InteractiveAgent
from src.runtime.subgoal_planner import (
    ACTIVE,
    BLOCKED,
    PENDING,
    SATISFIED,
    SubgoalPlanner,
)


def g1(memory="short_term"):
    return AgentGenome("cot", memory, "self_critique", "balanced", 64)


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


# ---------------- Gate A: semantics ----------------
def test_parse_put_alarmclock_in_dresser():
    s = parse_goal("put a alarmclock in dresser.")
    assert s.target_object == "alarmclock"
    assert s.target_receptacle == "dresser"
    assert s.required_relation in ("in", "to")
    assert s.task_family == "pick_and_place_simple"
    assert s.parse_ok


def test_parse_look_at_book_under_desklamp():
    s = parse_goal("look at book under the desklamp")
    assert s.target_object == "book"
    assert "desklamp" in s.target_receptacle
    assert s.task_family == "look_at_obj_in_light"
    assert s.parse_ok


def test_parse_move_and_place_forms():
    a = parse_goal("move an alarmclock to dresser")
    assert a.target_object == "alarmclock"
    assert a.target_receptacle == "dresser"
    b = parse_goal("place a book on desk")
    assert b.target_object == "book"
    assert b.target_receptacle == "desk"
    assert b.required_relation in ("on", "to")


def test_parse_unknown_when_incomplete():
    s = parse_goal("do something mysterious")
    assert s.target_object == UNKNOWN or s.parse_ok is False


def test_light_on_not_in_held():
    from src.diagnostics.shared_repair import ActionObservationRecorder, StepRecord

    r = ActionObservationRecorder()
    r.record(StepRecord(1, "x", "use desklamp 1", "You turn on the desklamp 1."))
    assert "light_on" not in r.held_objects()
    wf = r.world_facts()
    assert wf.get("light_on") is True


def test_memory_none_gets_zero_history():
    from src.diagnostics.shared_repair import ActionObservationRecorder, StepRecord, format_repaired_prompt_block

    r = ActionObservationRecorder()
    for i in range(5):
        r.record(StepRecord(i + 1, f"o{i}", f"a{i}", f"o{i+1}"))
    block = format_repaired_prompt_block("g", r, {}, {"memory_strategy": "none"}, memory_k=0)
    assert "Recent Actions and Feedback:" not in block
    block1 = format_repaired_prompt_block("g", r, {}, {"memory_strategy": "short_term"}, memory_k=1)
    assert "Recent Actions and Feedback:" in block1
    # k=0 direct
    assert r.history_lines(k=0) == []
    assert len(r.history_lines(k=2)) == 2
    assert len(r.history_lines()) == 5  # k=None still all for diagnostics


def test_task_type_derived_from_goal():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="grounded_planner_v1")
    a.select_action("You are in a room.", ["look"], goal="put a alarmclock in dresser")
    assert a._task_type == "pick_and_place_simple"


# ---------------- ActionSpec ----------------
def test_action_spec_mapping():
    assert parse_action("go to shelf 3").action_type == "NAVIGATE"
    assert parse_action("take book 2 from sidetable 1").action_type == "PICKUP"
    assert parse_action("move alarmclock 1 to dresser 1").action_type == "PLACE"
    assert parse_action("use desklamp 1").action_type == "USE_TOOL"
    assert parse_action("open drawer 2").action_type == "OPEN"
    assert parse_action("look").action_type == "LOOK"
    bad = parse_action("fly to moon")
    assert bad.action_type == "UNKNOWN" and bad.parse_ok is False


def test_relevant_candidates_only_from_admissible():
    adm = ["go to shelf 1", "go to shelf 3", "take alarmclock 1 from shelf 3", "look"]
    from src.runtime.subgoal_planner import Subgoal

    c = relevant_candidates(adm, subgoal=Subgoal(kind="ACQUIRE_TARGET", target="alarmclock"))
    assert all(x.raw_command in adm for x in c)
    assert any(x.action_type == "PICKUP" for x in c)


# ---------------- Subgoal transitions (F2) ----------------
def test_subgoal_transition_discover_acquire_place():
    from src.runtime.goal_grounding import parse_goal

    spec = parse_goal("put a alarmclock in dresser")
    p = SubgoalPlanner(spec)
    sg = p.active_subgoal()
    assert sg.kind == "EXPLORE"
    # explore
    p.update_from_feedback("go to shelf 1", "room", "You arrive at shelf 1. You see a pencil 1.")
    sg = p.active_subgoal()
    assert sg is not None and sg.kind in ("LOCATE_TARGET", "EXPLORE")
    # discover
    p.update_from_feedback("go to shelf 3", "shelf1", "You arrive at shelf 3. You see a alarmclock 1.")
    sg = p.active_subgoal()
    assert sg.kind in ("LOCATE_TARGET", "ACQUIRE_TARGET", "EXPLORE")
    # locate satisfied → acquire
    for _ in range(3):
        s = p.active_subgoal()
        if s and s.kind == "LOCATE_TARGET":
            p.update_from_feedback("examine shelf 3", "s3", "You see a alarmclock 1.")
        s = p.active_subgoal()
        if s and s.kind == "ACQUIRE_TARGET":
            break
        p.update_from_feedback("go to shelf 3", "x", "You arrive at shelf 3. You see a alarmclock 1.")
    sg = p.active_subgoal()
    assert sg.kind == "ACQUIRE_TARGET"
    p.update_from_feedback("take alarmclock 1 from shelf 3", "s3", "You pick up the alarmclock 1 from the shelf 3.")
    assert any("alarmclock" in h.lower() for h in p.held)
    # advance through remaining
    for _ in range(6):
        s = p.active_subgoal()
        if s is None:
            break
        if s.kind == "LOCATE_DEST":
            p.update_from_feedback("go to dresser 1", "x", "You arrive at dresser 1.")
        elif s.kind == "PLACE_TARGET":
            p.update_from_feedback("move alarmclock 1 to dresser 1", "d", "You move the alarmclock 1 to the dresser 1.")
        elif s.kind == "VERIFY_SUCCESS":
            p.mark_native_won(True)
        else:
            p.update_from_feedback("look", "x", "You see nothing new.")
    assert p.world_facts.get("alarmclock_placed") is True or not p.active_subgoal()
    assert p.active_subgoal() is None or p.active_subgoal().kind == "VERIFY_SUCCESS"


def test_pickup_failure_updates_state():
    from src.runtime.goal_grounding import parse_goal

    p = SubgoalPlanner(parse_goal("put a alarmclock in dresser"))
    for _ in range(3):
        p.update_from_feedback("go to shelf 1", "r", "You arrive at shelf 1. You see a alarmclock 1.")
    sg = p.active_subgoal()
    # force to acquire
    for s in p.subgoals:
        if s.kind == "EXPLORE":
            s.status = SATISFIED
        if s.kind == "LOCATE_TARGET":
            s.status = SATISFIED
    sg = p.active_subgoal()
    assert sg.kind == "ACQUIRE_TARGET"
    p.update_from_feedback("take alarmclock 1 from shelf 1", "s", "You can't see any such thing.")
    assert "alarmclock" not in p.held


# ---------------- Gate C: runtime isolation ----------------
def test_current_runtime_unchanged():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="current")
    a.select_action("o", ["look"], goal="g")
    assert "Active Subgoal" not in llm.prompts[0]
    assert "Observed Progress" not in llm.prompts[0]


def test_grounded_planner_prompt_has_subgoal_and_candidates():
    llm = ScriptedLLM(["go to shelf 1", "take alarmclock 1 from shelf 1"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="grounded_planner_v1")
    a.select_action("You are in a room.", ["go to shelf 1", "look", "take alarmclock 1 from shelf 1"],
                    goal="put a alarmclock in dresser")
    assert "Active Subgoal" in llm.prompts[0]
    assert "Legal Action Candidates" in llm.prompts[0]
    a.observe("go to shelf 1", "room", "You arrive at shelf 1. You see a alarmclock 1.")
    a.select_action("You arrive at shelf 1. You see a alarmclock 1.",
                    ["take alarmclock 1 from shelf 1", "look"], goal="put a alarmclock in dresser")
    assert "Active Subgoal" in llm.prompts[1]


def test_shared_repaired_still_works():
    llm = ScriptedLLM(["look"])
    a = InteractiveAgent(g1(), llm, horizon=10, runtime_variant="shared_repaired")
    a.select_action("o", ["look"], goal="look at book under the desklamp")
    assert "Observed Progress" in llm.prompts[0]


def test_no_oracle_in_new_modules():
    import inspect

    import src.runtime.action_semantics as am
    import src.runtime.goal_grounding as gg
    import src.runtime.subgoal_planner as sp

    for m in (gg, am, sp):
        src = inspect.getsource(m)
        for banned in ("traj_data", "high_pddl", "game_id →", "shelf 3", "sidetable 2", "expert_action"):
            assert banned not in src, f"{m.__name__} contains {banned}"


def test_grounding_blocked_when_no_admissible():
    from src.runtime.action_semantics import relevant_candidates

    assert relevant_candidates([], subgoal=None) == []
