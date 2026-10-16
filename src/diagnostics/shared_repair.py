"""Shared agent repair: Action–Observation recorder + stagnation + goal-state.

Evidence rules (P0, Stage 1.6):
  - Task-description text is NEVER object-discovery evidence.
  - Object state is a transition machine, not a monotonic flag.
  - Action effects require matching environment feedback, not command names.
  - No expert/oracle data may enter the runtime path.

Used by InteractiveAgent only when runtime_variant == "shared_repaired".
Genome memory_strategy still controls how many history lines the LLM sees.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Object / tool observation states
NOT_OBSERVED = "NOT_OBSERVED"
OBSERVED = "OBSERVED"
ACQUIRED = "ACQUIRED"
RELEASED = "RELEASED"
UNKNOWN = "UNKNOWN"

TASK_DESC_RE = re.compile(r"^\s*your task is to:.*$", re.I | re.M)

_LOC_RE = re.compile(
    r"(?:you arrive at|on the|facing the|you are facing the) "
    r"((?:desk|shelf|bed|drawer|sidetable|dresser|safe|garbagecan|table|cabinet|armchair|laundryhamper|toilet|bathtub|counter|stove|sink|mirror)\s+\d+)",
    re.I,
)

# Feedback that confirms an effect (not just a command being sent)
_PICKUP_OK_RE = re.compile(r"you pick up the (.+?)(?: from |\.|$)", re.I)
_PICKUP_FAIL_RE = re.compile(r"(?:can'?t|cannot|unable|nothing happens|you are not holding|there is no)", re.I)
_RELEASE_RE = re.compile(r"(?:you (?:put|move|drop) the (.+?) (?:to|on|in|onto))", re.I)
_LIGHT_ON_RE = re.compile(r"you turn on the (.+?)\.?\s*$", re.I | re.M)
_LIGHT_ALREADY_RE = re.compile(r"(?:already (?:on|lit))", re.I)
_PLACE_OK_RE = re.compile(r"you (?:put|move) the (.+?) (?:to|on|in|onto) the (.+?)\.?\s*$", re.I | re.M)


def strip_task_description(text: str) -> str:
    return TASK_DESC_RE.sub("", text or "")


def canonical_state(observation: str) -> str:
    return re.sub(r"\s+", " ", strip_task_description(observation or "")).strip().lower()


def _norm(s: str) -> str:
    return (s or "").lower().replace(" ", "")


@dataclass
class StepRecord:
    step_index: int
    observation_before: str
    action: str
    observation_after: str
    parse_ok: bool = True
    used_fallback: bool = False


@dataclass
class ObjectState:
    name: str
    state: str = NOT_OBSERVED  # NOT_OBSERVED|OBSERVED|ACQUIRED|RELEASED|UNKNOWN
    last_evidence: str = ""


class ActionObservationRecorder:
    """Shared state record. Genome memory_strategy picks the history window."""

    def __init__(self, max_events: int = 64) -> None:
        self.max_events = max_events
        self.events: List[StepRecord] = []
        self.visited_locations: List[str] = []
        self.object_states: Dict[str, ObjectState] = {}
        self.completed_subgoals: List[str] = []
        self.repeated_actions: List[str] = []

    # ---- evidence-safe object state transitions ----
    def _touch_object(self, name: str, new_state: str, evidence: str) -> None:
        key = _norm(name)
        if not key:
            return
        st = self.object_states.get(key)
        if st is None:
            st = ObjectState(name=name.strip())
            self.object_states[key] = st
        # transitions: allow OBSERVED->ACQUIRED->RELEASED; UNKNOWN is sticky-lower
        order = {NOT_OBSERVED: 0, OBSERVED: 1, UNKNOWN: 1, RELEASED: 2, ACQUIRED: 3}
        if st.state == ACQUIRED and new_state == OBSERVED:
            return  # still holding is stronger than merely seen
        st.state = new_state
        st.last_evidence = evidence[:160]

    def _scan_feedback(self, rec: StepRecord) -> None:
        after = strip_task_description(rec.observation_after or "")
        before = strip_task_description(rec.observation_before or "")
        combined = (before + "\n" + after).lower()
        action_l = (rec.action or "").lower()

        # 1) Observation-only mentions (discovery)
        for m in re.finditer(
            r"\b(?:see|seeing|there is|you see) (?:a |an |the )?([a-z][a-z0-9 ]{1,30}?)\b",
            after.lower(),
        ):
            raw = m.group(1).strip()
            # drop trailing noise words
            raw = re.split(r",| and |\.| on | in | from ", raw)[0].strip()
            if 2 <= len(raw) <= 30:
                key = _norm(raw)
                if key and key not in self.object_states:
                    self._touch_object(raw, OBSERVED, f"observed: {raw}")

        # 2) Pickup success ONLY on feedback phrase
        m = _PICKUP_OK_RE.search(after)
        if m:
            self._touch_object(m.group(1).strip().rstrip("."), ACQUIRED, f"pickup feedback: {rec.action}")
        elif action_l.startswith(("take ", "pick up")):
            # command sent but no pickup confirmation
            obj_m = re.match(r"(?:take|pick up) (.+?)(?: from |$)", action_l)
            obj = obj_m.group(1).strip() if obj_m else ""
            if _PICKUP_FAIL_RE.search(after):
                if obj:
                    self._touch_object(obj, UNKNOWN, f"pickup failed: {after[:80]}")
            elif obj and _norm(obj) not in self.object_states:
                self._touch_object(obj, UNKNOWN, f"pickup unconfirmed: {after[:80]}")

        # 3) Release / placement
        m = _PLACE_OK_RE.search(after)
        if m:
            self._touch_object(m.group(1).strip(), RELEASED, f"place feedback: {rec.action}")
        elif action_l.startswith(("move ", "put ", "drop ")):
            obj_m = re.match(r"(?:move|put|drop) (.+?)(?: to | on | in | onto |$)", action_l)
            obj = obj_m.group(1).strip() if obj_m else ""
            if obj and _norm(obj) in self.object_states:
                # only mark released if feedback acknowledges placement
                if re.search(r"(?:you (?:put|move|drop)|placed|moved)", after, re.I):
                    self._touch_object(obj, RELEASED, f"place via action+fb: {rec.action}")
                else:
                    self._touch_object(obj, UNKNOWN, f"place unconfirmed: {after[:80]}")

        # 4) Light / tool toggle
        if action_l.startswith("use ") and "lamp" in action_l:
            if _LIGHT_ON_RE.search(after) or "turn on" in after.lower():
                key = "light_on"
                self._touch_object(key, ACQUIRED, f"light on: {after[:80]}")
                if "light_on" not in self.completed_subgoals:
                    self.completed_subgoals.append("light_on")
            elif _LIGHT_ALREADY_RE.search(after):
                self._touch_object("light_on", ACQUIRED, f"light already on: {after[:80]}")
            else:
                self._touch_object("light_on", UNKNOWN, f"use lamp unconfirmed: {after[:80]}")

        # 5) explicit holdings in text
        if "you are holding" in combined or "you pick up" in combined:
            pass  # already handled
        if re.search(r"you (?:put|move|drop) the", after, re.I):
            pass

    def record(self, rec: StepRecord) -> None:
        self.events.append(rec)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]
        loc = self._location_of(rec.observation_after)
        if loc and loc not in self.visited_locations:
            self.visited_locations.append(loc)
        self._scan_feedback(rec)
        if rec.action and self._is_repeat(rec):
            self.repeated_actions.append(rec.action)

    def _location_of(self, obs: str) -> Optional[str]:
        m = _LOC_RE.search(strip_task_description(obs or ""))
        return m.group(1).lower() if m else None

    def _is_repeat(self, rec: StepRecord) -> bool:
        pair = (canonical_state(rec.observation_before), rec.action)
        return any(
            (canonical_state(e.observation_before), e.action) == pair for e in self.events[:-1]
        )

    def held_objects(self) -> List[str]:
        """Physical objects only — world/tool facts (e.g. light_on) excluded."""
        skip = {"light_on"}
        return [
            o.name for o in self.object_states.values()
            if o.state == ACQUIRED and _norm(o.name) not in skip
        ]

    def world_facts(self) -> Dict[str, Any]:
        """Tool / environment facts separated from inventory."""
        facts = {}
        lo = self.object_states.get("light_on")
        if lo:
            facts["light_on"] = lo.state == ACQUIRED
            if lo.state == UNKNOWN:
                facts["light_on"] = UNKNOWN
        return facts

    def summary(self) -> Dict[str, Any]:
        return {
            "n_events": len(self.events),
            "visited_locations": list(self.visited_locations),
            "held_objects": self.held_objects(),
            "object_states": {
                k: {"state": v.state, "evidence": v.last_evidence}
                for k, v in self.object_states.items()
            },
            "completed_subgoals": list(self.completed_subgoals),
            "repeated_actions": list(self.repeated_actions),
        }

    def history_lines(self, k: Optional[int] = None) -> List[str]:
        """k=None -> all retained events; k=0 -> empty; k>0 -> last k."""
        if k is not None and k <= 0:
            return []
        rows = self.events if k is None else self.events[-k:]
        return [
            f"step{e.step_index}: did={e.action} | feedback={canonical_state(e.observation_after)[:70]}"
            for e in rows
        ]


@dataclass
class StagnationDetector:
    window: int = 3
    same_obs_threshold: int = 3

    def check(self, recorder: ActionObservationRecorder) -> Dict[str, Any]:
        ev = recorder.events
        if len(ev) < self.window:
            return {"stagnation": False, "rslr_window": 0.0, "same_observation_run": 0}
        recent = ev[-self.window :]
        pairs = [(canonical_state(e.observation_before), e.action) for e in recent]
        unique_pairs = len(set(pairs))
        same_obs_run = 1
        for i in range(len(recent) - 1, 0, -1):
            if canonical_state(recent[i].observation_after) == canonical_state(
                recent[i - 1].observation_after
            ):
                same_obs_run += 1
            else:
                break
        stagnant = unique_pairs == 1 or same_obs_run >= self.same_obs_threshold
        return {
            "stagnation": stagnant,
            "rslr_window": 1.0 - unique_pairs / max(1, len(pairs)),
            "same_observation_run": same_obs_run,
        }


def goal_state_tracker(
    task_type: str,
    recorder: ActionObservationRecorder,
    goal: str,
    *,
    native_won: Optional[bool] = None,
) -> Dict[str, Any]:
    """Evidence-driven goal flags. Goal text is parsed for OBJECT NAMES only —
    never for discovery/acquisition truth. native_won is NEVER inferred."""
    goal_l = (goal or "").lower()
    # parse target object/receptacle names from goal wording (names only)
    obj, recep = "", ""
    m = re.search(r"look at (?:a |an |the )?(\w+)", goal_l)
    if m:
        obj = m.group(1)
    m2 = re.search(r"(?:under|on|in|onto) (?:a |an |the )?(?:lit |the )?(\w+)", goal_l)
    if m2:
        recep = m2.group(1)
    if not obj:
        m3 = re.search(r"move (?:a |an |the )?(\w+)", goal_l)
        if m3:
            obj = m3.group(1)
    if not recep:
        m4 = re.search(r"(?:to|onto) (?:a |an |the )?(\w+)", goal_l)
        if m4:
            recep = m4.group(1)

    def state_of(name: str) -> str:
        if not name:
            return NOT_OBSERVED
        key = _norm(name)
        order = {NOT_OBSERVED: 0, UNKNOWN: 1, OBSERVED: 2, RELEASED: 3, ACQUIRED: 4}
        best = NOT_OBSERVED
        for k, v in recorder.object_states.items():
            if key == k or key in k or k in key:
                if order.get(v.state, 0) > order.get(best, 0):
                    best = v.state
        return best

    obj_state = state_of(obj) if obj else NOT_OBSERVED
    light_state = state_of("light_on")
    found = obj_state in (OBSERVED, ACQUIRED, RELEASED)
    acquired = obj_state == ACQUIRED
    released = obj_state == RELEASED
    lit = light_state == ACQUIRED

    if task_type in ("look_at_obj_in_light",) or ("under" in goal_l or "lit" in goal_l):
        manipulation = lit and acquired  # holding object with light on
    elif task_type in ("pick_and_place_simple",) or "move" in goal_l:
        # placement requires release feedback naming object AND target
        manipulation = False
        for e in recorder.events:
            after = strip_task_description(e.observation_after or "")
            pm = _PLACE_OK_RE.search(after)
            if pm and obj and _norm(obj) in _norm(pm.group(1)) and recep and _norm(recep) in _norm(pm.group(2)):
                manipulation = True
                break
    else:
        manipulation = False

    return {
        "goal_text": goal,
        "target_object_name": obj,
        "target_receptacle_name": recep,
        "object_state": obj_state,
        "object_found": found,
        "object_acquired": acquired,
        "object_released": released,
        "light_turned_on": lit,
        "manipulation_completed": manipulation,
        "native_success_confirmed": bool(native_won) if native_won is not None else False,
    }


def format_repaired_prompt_block(
    goal: str,
    recorder: ActionObservationRecorder,
    stagnation: Dict[str, Any],
    goal_state: Dict[str, Any],
    *,
    memory_k: Optional[int] = 3,
) -> str:
    """Frozen prompt template (STAGE1_6_PROMPT_V1). Do not edit mid-experiment.

    memory_k: none -> 0 (no history lines); short_term -> 1; others -> 3.
    """
    k = 0 if memory_k is None else int(memory_k)
    if goal_state.get("memory_strategy") == "none":
        k = 0
    elif goal_state.get("memory_strategy") == "short_term":
        k = 1
    lines = [
        "Observed Progress:",
        f"- target object ({goal_state.get('target_object_name') or '?'}): {goal_state.get('object_state')}",
        f"- currently held: {', '.join(recorder.held_objects()) or 'none confirmed'}",
        f"- light turned on: {'yes' if goal_state.get('light_turned_on') else 'not confirmed'}",
        f"- native task completed: {'yes' if goal_state.get('native_success_confirmed') else 'no'}",
    ]
    hist = recorder.history_lines(k=k)
    if hist:
        lines.append("Recent Actions and Feedback:")
        lines.extend(f"  {h}" for h in hist)
    if stagnation.get("stagnation"):
        lines.append(
            "Stagnation Warning: You have repeated the same action in an unchanged "
            "state without making new progress. Try a different location or action."
        )
    return "\n".join(lines)
