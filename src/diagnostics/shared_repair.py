"""Shared agent repair: Action–Observation recorder + stagnation detector.

OFFLINE / DIAGNOSTIC ONLY. Does not modify InteractiveAgent decision path.
Default-off; future integration must be a shared baseline for ALL methods.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def canonical_state(observation: str) -> str:
    """Normalize observation text for equality checks."""
    return re.sub(r"\s+", " ", (observation or "").strip()).lower()


@dataclass
class StepRecord:
    step_index: int
    observation_before: str
    action: str
    observation_after: str
    parse_ok: bool = True
    used_fallback: bool = False


@dataclass
class ActionObservationRecorder:
    """Minimal shared state record (all methods can use this infrastructure).

    Genome memory_strategy still decides HOW MUCH history is shown to the LLM.
    """

    max_events: int = 64
    events: List[StepRecord] = field(default_factory=list)
    visited_locations: List[str] = field(default_factory=list)
    acquired_objects: List[str] = field(default_factory=list)
    completed_subgoals: List[str] = field(default_factory=list)
    failed_or_repeated: List[str] = field(default_factory=list)

    def record(self, rec: StepRecord) -> None:
        self.events.append(rec)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
        loc = self._location_of(rec.observation_after)
        if loc and loc not in self.visited_locations:
            self.visited_locations.append(loc)
        m = re.search(r"you pick up the ([a-z0-9 ]+?) from", rec.observation_after or "", re.I)
        if m:
            obj = m.group(1).strip()
            if obj not in self.acquired_objects:
                self.acquired_objects.append(obj)
        if rec.action and self._is_repeat(rec):
            self.failed_or_repeated.append(rec.action)

    def _location_of(self, obs: str) -> Optional[str]:
        m = re.search(
            r"(?:you arrive at|on the|facing the) ((?:desk|shelf|bed|drawer|sidetable|dresser|safe|garbagecan|table|cabinet|armchair|laundryhamper)\s+\d+)",
            obs or "",
            re.I,
        )
        return m.group(1).lower() if m else None

    def _is_repeat(self, rec: StepRecord) -> bool:
        pair = (canonical_state(rec.observation_before), rec.action)
        prior = sum(
            1
            for e in self.events[:-1]
            if (canonical_state(e.observation_before), e.action) == pair
        )
        return prior >= 1

    def summary(self) -> Dict[str, Any]:
        return {
            "n_events": len(self.events),
            "visited_locations": list(self.visited_locations),
            "acquired_objects": list(self.acquired_objects),
            "completed_subgoals": list(self.completed_subgoals),
            "repeated_actions": list(self.failed_or_repeated),
        }

    def history_lines(self, k: Optional[int] = None) -> List[str]:
        """What MAY be shown to the LLM; Genome memory_strategy picks k."""
        rows = self.events if k is None else self.events[-k:]
        return [
            f"step{e.step_index}: saw={canonical_state(e.observation_before)[:60]} | did={e.action} | got={canonical_state(e.observation_after)[:60]}"
            for e in rows
        ]


@dataclass
class StagnationDetector:
    """Diagnostic-only repeated state-action detector. Does NOT override actions."""

    window: int = 3
    same_obs_threshold: int = 3

    def check(self, recorder: ActionObservationRecorder) -> Dict[str, Any]:
        ev = recorder.events
        if len(ev) < self.window:
            return {"stagnation": False, "rslr_window": 0.0}
        recent = ev[-self.window:]
        pairs = [(canonical_state(e.observation_before), e.action) for e in recent]
        unique_pairs = len(set(pairs))
        same_obs_run = 1
        for i in range(len(recent) - 1, 0, -1):
            if canonical_state(recent[i].observation_after) == canonical_state(recent[i - 1].observation_after):
                same_obs_run += 1
            else:
                break
        stagnant = unique_pairs == 1 or same_obs_run >= self.same_obs_threshold
        return {
            "stagnation": stagnant,
            "rslr_window": 1.0 - unique_pairs / max(1, len(pairs)),
            "same_observation_run": same_obs_run,
        }


def goal_state_tracker(task_type: str, recorder: ActionObservationRecorder, goal: str) -> Dict[str, Any]:
    """Evidence-driven goal flags from recorder only (no oracle)."""
    goal_l = (goal or "").lower()
    if task_type == "look_at_obj_in_light" or "under" in goal_l or "lit" in goal_l:
        obj_m = re.search(r"(?:look at|a) (\w+)", goal_l)
        obj = obj_m.group(1) if obj_m else ""
        found = any(obj and obj in (e.observation_after + e.observation_before).lower() for e in recorder.events)
        acquired = any(obj and obj in a.lower() for a in recorder.acquired_objects) or any(
            obj and obj in e.action.lower() and e.action.lower().startswith("take") for e in recorder.events
        )
        lit = any("lamp" in e.action.lower() and e.action.lower().startswith("use") for e in recorder.events)
        return {
            "object_found": found,
            "object_acquired": acquired,
            "required_tool_found": lit or any("lamp" in (e.observation_after or "").lower() for e in recorder.events),
            "manipulation_completed": lit and acquired,
            "native_success_confirmed": False,
        }
    if task_type == "pick_and_place_simple" or "move" in goal_l:
        found = bool(recorder.events)
        acquired = bool(recorder.acquired_objects)
        placed = any(
            e.action.lower().startswith(("move ", "put ")) for e in recorder.events
        )
        return {
            "object_found": found,
            "object_acquired": acquired,
            "required_tool_found": True,
            "manipulation_completed": placed,
            "native_success_confirmed": False,
        }
    return {
        "object_found": False,
        "object_acquired": False,
        "required_tool_found": False,
        "manipulation_completed": False,
        "native_success_confirmed": False,
    }
