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


def relevant_candidates(admissible, goal_spec=None, subgoal=None, exclude_actions=None):
    """Select legal candidates related to the active subgoal (never invents cmds)."""
    exclude = set(exclude_actions or [])
    specs = [s for s in parse_admissible(admissible) if s.raw_command not in exclude]
    if subgoal is None:
        return specs
    kind = getattr(subgoal, "kind", "")
    target = getattr(subgoal, "target", "") or ""
    tn = target.lower().replace(" ", "")
    matched = []
    for s in specs:
        blob = (s.object + " " + s.target + " " + s.source).lower().replace(" ", "")
        if kind == "EXPLORE" and s.action_type == NAVIGATE:
            matched.append(s)
        elif kind in ("LOCATE_TARGET", "ACQUIRE_TARGET") and tn and tn in blob:
            matched.append(s)
        elif kind == "ACQUIRE_TARGET" and s.action_type == PICKUP:
            matched.append(s)
        elif kind == "LOCATE_TOOL" and s.action_type in (NAVIGATE, INSPECT):
            matched.append(s)
        elif kind == "USE_TOOL" and s.action_type == USE_TOOL:
            matched.append(s)
        elif kind == "PLACE_TARGET" and s.action_type == PLACE:
            matched.append(s)
        elif kind == "VERIFY_SUCCESS" and s.action_type in (LOOK, INSPECT, USE_TOOL, PLACE):
            matched.append(s)
    if matched:
        return matched
    # fallback: navigation helps discovery; then everything legal
    nav = [s for s in specs if s.action_type == NAVIGATE]
    return nav or specs
