"""ALFWorld action semantics: parse real admissible commands into ActionSpec.

Deterministic parser. Input MUST come from the live admissible_commands list.
Never invents commands; unknown forms map to UNKNOWN.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

UNKNOWN = "UNKNOWN"

NAVIGATE = "NAVIGATE"
INSPECT = "INSPECT"
OPEN = "OPEN"
PICKUP = "PICKUP"
PLACE = "PLACE"
USE_TOOL = "USE_TOOL"
LOOK = "LOOK"
CLOSE = "CLOSE"


@dataclass
class ActionSpec:
    action_type: str = UNKNOWN
    object: str = ""
    source: str = ""
    target: str = ""
    raw_command: str = ""
    parse_ok: bool = False

    def to_dict(self):
        return {
            "action_type": self.action_type,
            "object": self.object,
            "source": self.source,
            "target": self.target,
            "raw_command": self.raw_command,
            "parse_ok": self.parse_ok,
        }


def parse_action(raw: str) -> ActionSpec:
    cmd = (raw or "").strip()
    spec = ActionSpec(raw_command=cmd)
    low = cmd.lower()
    if not low:
        return spec

    if low == "look" or low.startswith("look "):
        spec.action_type = LOOK
        spec.parse_ok = True
        return spec

    m = re.match(r"go to (.+)$", low)
    if m:
        spec.action_type = NAVIGATE
        spec.target = m.group(1).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"examine (.+)$", low)
    if m:
        spec.action_type = INSPECT
        spec.object = m.group(1).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"open (.+)$", low)
    if m:
        spec.action_type = OPEN
        spec.target = m.group(1).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"close (.+)$", low)
    if m:
        spec.action_type = CLOSE
        spec.target = m.group(1).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"(?:take|pick up) (.+?) from (.+)$", low)
    if m:
        spec.action_type = PICKUP
        spec.object = m.group(1).strip()
        spec.source = m.group(2).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"move (.+?) to (.+)$", low)
    if m:
        spec.action_type = PLACE
        spec.object = m.group(1).strip()
        spec.target = m.group(2).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"put (.+?) (?:in|on|onto|into) (.+)$", low)
    if m:
        spec.action_type = PLACE
        spec.object = m.group(1).strip()
        spec.target = m.group(2).strip()
        spec.parse_ok = True
        return spec

    m = re.match(r"use (.+)$", low)
    if m:
        spec.action_type = USE_TOOL
        spec.object = m.group(1).strip()
        spec.target = m.group(1).strip()
        spec.parse_ok = True
        return spec

    if low.startswith("turn on "):
        spec.action_type = USE_TOOL
        spec.object = low[len("turn on "):].strip()
        spec.parse_ok = True
        return spec

    spec.action_type = UNKNOWN
    spec.parse_ok = False
    return spec


def parse_admissible(commands) -> list:
    """Parse a list of admissible commands; keep only those in the input list."""
    out = []
    for c in commands or []:
        out.append(parse_action(str(c)))
    return out


def relevant_candidates(admissible, goal_spec=None, subgoal=None, exclude_actions=None,
                        held_objects=None):
    """Select and rank legal candidates related to the active subgoal.

    Target-relevant actions always outrank unrelated ones. Never invents
    commands; output ⊆ input admissible.
    """
    exclude = set(exclude_actions or [])
    specs = [s for s in parse_admissible(admissible) if s.raw_command not in exclude]
    if not specs:
        return []
    if subgoal is None:
        return specs
    kind = getattr(subgoal, "kind", "")
    target = getattr(subgoal, "target", "") or ""
    tn = target.lower().replace(" ", "")
    goal_obj = ""
    goal_recep = ""
    if goal_spec is not None:
        goal_obj = (getattr(goal_spec, "target_object", "") or "").lower().replace(" ", "")
        goal_recep = (getattr(goal_spec, "target_receptacle", "") or "").lower().replace(" ", "")
    held = [h.lower().replace(" ", "") for h in (held_objects or [])]

    def relevance(s) -> float:
        blob = (s.object + " " + s.target + " " + s.source).lower().replace(" ", "")
        score = 0.0
        # target object match is strongest
        if goal_obj and goal_obj in blob:
            score += 10
        if tn and tn in blob:
            score += 6
        if goal_recep and goal_recep in blob:
            score += 4
        if kind == "EXPLORE":
            if s.action_type == NAVIGATE:
                score += 5
        elif kind in ("LOCATE_TARGET", "ACQUIRE_TARGET"):
            if s.action_type == PICKUP and goal_obj and goal_obj in blob:
                score += 10
            elif s.action_type == PICKUP:
                score -= 4  # unrelated pickup
            elif s.action_type == NAVIGATE:
                score += 2
        elif kind == "ACQUIRE_TARGET":
            if s.action_type == PICKUP:
                score += 8
        elif kind in ("LOCATE_TOOL",):
            if s.action_type == USE_TOOL:
                score += 8
            if s.action_type == NAVIGATE:
                score += 3
        elif kind == "USE_TOOL":
            if s.action_type == USE_TOOL:
                score += 10
        elif kind == "LOCATE_DEST":
            if s.action_type == NAVIGATE:
                score += 5
        elif kind == "PLACE_TARGET":
            if s.action_type == PLACE:
                score += 10
                if goal_obj and goal_obj in blob:
                    score += 4
            elif s.action_type == PICKUP:
                score -= 4
        elif kind == "VERIFY_SUCCESS":
            if s.action_type in (LOOK, INSPECT):
                score += 3
        return score

    ranked = sorted(specs, key=lambda s: (-relevance(s), s.raw_command))
    # keep only reasonably relevant unless nothing matches (then nav, then all)
    top = [s for s in ranked if relevance(s) > 0]
    if top:
        return top
    nav = [s for s in ranked if s.action_type == NAVIGATE]
    return nav or ranked
