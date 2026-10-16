"""Offline tests for shared repair recorder / stagnation / goal tracker."""
from __future__ import annotations

from src.diagnostics.shared_repair import (
    ActionObservationRecorder,
    StagnationDetector,
    canonical_state,
    goal_state_tracker,
    StepRecord,
)


def _rec(i, before, action, after):
    return StepRecord(step_index=i, observation_before=before, action=action, observation_after=after)


def test_recorder_tracks_locations_and_actions():
    r = ActionObservationRecorder()
    r.record(_rec(1, "room", "go to desk 1", "You arrive at desk 1. On the desk 1, you see a book 2."))
    r.record(_rec(2, "desk", "take book 2 from desk 1", "You pick up the book 2 from the desk 1."))
    s = r.summary()
    assert s["n_events"] == 2
    assert any("desk" in x for x in s["visited_locations"])
    assert any("book" in x for x in s["held_objects"])


def test_stagnation_detects_repeat():
    r = ActionObservationRecorder()
    obs = "On the desk 1, you see a pen 1."
    for i in range(4):
        r.record(_rec(i + 1, obs, "examine desk 1", obs))
    d = StagnationDetector(window=3).check(r)
    assert d["stagnation"] is True


def test_stagnation_not_flagged_on_progress():
    r = ActionObservationRecorder()
    r.record(_rec(1, "a", "go to desk 1", "arrive desk"))
    r.record(_rec(2, "arrive desk", "take book 2", "got book"))
    r.record(_rec(3, "got book", "go to shelf 1", "arrive shelf"))
    d = StagnationDetector(window=3).check(r)
    assert d["stagnation"] is False


def test_history_lines_count():
    r = ActionObservationRecorder()
    for i in range(5):
        r.record(_rec(i + 1, f"obs{i}", f"act{i}", f"obs{i+1}"))
    assert len(r.history_lines()) == 5
    assert len(r.history_lines(k=2)) == 2
    # genome policy would choose k; recorder stays complete


def test_goal_tracker_look_at_light():
    r = ActionObservationRecorder()
    r.record(_rec(1, "room", "go to sidetable 1", "You see a book 2 on the sidetable 1."))
    r.record(_rec(2, "sidetable", "take book 2 from sidetable 1", "You pick up the book 2."))
    r.record(_rec(3, "holding", "use desklamp 1", "You turn on the desklamp 1."))
    g = goal_state_tracker("look_at_obj_in_light", r, "look at book under the desklamp.")
    assert g["object_found"] is True
    assert g["object_acquired"] is True
    assert g["manipulation_completed"] is True
    assert g["native_success_confirmed"] is False  # never auto-win


def test_no_oracle_peek():
    # tracker must not invent success without native won flag
    r = ActionObservationRecorder()
    r.record(_rec(1, "x", "look", "y"))
    g = goal_state_tracker("pick_and_place_simple", r, "Move an alarm clock to the dresser")
    assert g["native_success_confirmed"] is False


def test_canonical_state():
    assert canonical_state("  A   B\n") == "a b"
