"""Goal semantics: parse public task text into a structured GoalSpec.

Strictly public-text only. Never uses game files, expert trajectories, or
hidden state. Unknown fields stay UNKNOWN — no guessing from test answers.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

UNKNOWN = "UNKNOWN"

_FAMILY_PATTERNS = [
    (r"\blook at\b.*\bunder\b", "look_at_obj_in_light"),
    (r"\blook at\b.*\blit\b", "look_at_obj_in_light"),
    (r"\bput\b|\bplace\b|\bmove\b", "pick_and_place_simple"),
    (r"\bheat\b|\bcool\b", "heat_then_place"),
    (r"\bclean\b|\bpolish\b", "clean_then_place"),
    (r"\bslice\b", "slice_then_place"),
    (r"\bexamine\b", "look_at_obj_in_light"),
]

_ARTICLE = r"(?:(?:a|an|the)\s+)?"
# object names are 1–3 words of letters/digits (no hard-coded vocab)
_WORD = r"([a-z][a-z0-9]*(?:\s+[a-z][a-z0-9]*){0,2})"


@dataclass
class GoalSpec:
    task_family: str = UNKNOWN
    target_object: str = UNKNOWN
    target_receptacle: str = UNKNOWN
    required_tool: str = UNKNOWN
    required_relation: str = UNKNOWN  # in|on|under|look_under|look_with_light
    raw_goal: str = ""
    parse_ok: bool = False
    parse_notes: str = ""

    def to_dict(self):
        return {
            "task_family": self.task_family,
            "target_object": self.target_object,
            "target_receptacle": self.target_receptacle,
            "required_tool": self.required_tool,
            "required_relation": self.required_relation,
            "raw_goal": self.raw_goal,
            "parse_ok": self.parse_ok,
            "parse_notes": self.parse_notes,
        }


def parse_goal(text: str) -> GoalSpec:
    """Parse a public ALFWorld goal sentence into GoalSpec."""
    raw = (text or "").strip()
    goal = raw.lower()
    # strip leading "your task is to:" if present
    goal = re.sub(r"^(?:your task is to:?\s*)", "", goal).strip().rstrip(".")
    spec = GoalSpec(raw_goal=raw)

    # task family
    for pat, fam in _FAMILY_PATTERNS:
        if re.search(pat, goal):
            spec.task_family = fam
            break

    # look at OBJECT under/light SOURCE
    m = re.search(rf"look at\s+{_ARTICLE}{_WORD}\s+(?:under|beneath|with|by)\s+{_ARTICLE}(?:lit\s+)?{_WORD}", goal)
    if m:
        spec.target_object = m.group(1).strip()
        spec.target_receptacle = m.group(2).strip()
        spec.required_tool = m.group(2).strip()
        spec.required_relation = "look_under_light"
        spec.parse_ok = True
        spec.parse_notes = "look_at + under/with tool"
        return spec

    # look at OBJECT
    m = re.search(rf"look at\s+{_ARTICLE}{_WORD}", goal)
    if m and spec.target_object == UNKNOWN:
        spec.target_object = m.group(1).strip()
        spec.parse_notes = "look_at object only"

    # put/place OBJECT in/on RECEPTACLE
    m = re.search(
        rf"(?:put|place|move)\s+{_ARTICLE}{_WORD}\s+(?:in|into|on|onto|to)\s+{_ARTICLE}{_WORD}",
        goal,
    )
    if m:
        obj = m.group(1).strip()
        recep = m.group(2).strip()
        # avoid capturing trailing relation words as receptacle
        recep = re.split(r"\s+under\s+|\s+with\s+|\s+and\s+", recep)[0].strip()
        if spec.target_object == UNKNOWN:
            spec.target_object = obj
        if spec.target_receptacle == UNKNOWN:
            spec.target_receptacle = recep
        rel = "in" if re.search(r"\bin\b|\binto\b", goal) else "on" if re.search(r"\bon\b|\bonto\b", goal) else "to"
        spec.required_relation = rel
        if spec.task_family == UNKNOWN:
            spec.task_family = "pick_and_place_simple"
        spec.parse_ok = spec.target_object != UNKNOWN and spec.target_receptacle != UNKNOWN
        spec.parse_notes = (spec.parse_notes + "; " if spec.parse_notes else "") + "place relation"

    # explicit "in" without place verb already handled above
    if spec.target_object != UNKNOWN and spec.target_receptacle != UNKNOWN and spec.parse_ok:
        return spec

    # fallback notes
    if spec.target_object == UNKNOWN:
        spec.parse_notes += "; object UNKNOWN"
    if spec.target_receptacle == UNKNOWN and spec.task_family == "pick_and_place_simple":
        spec.parse_notes += "; receptacle UNKNOWN"
    if spec.task_family == UNKNOWN:
        spec.parse_notes += "; family UNKNOWN"
    return spec
