"""Evidence-driven subgoal planner for grounded_planner_v1.

Task-family subgoal sequences are GENERIC task relations — not expert routes.
Location/object instances come only from admissible_commands and env feedback.
No game-id to location maps. No expert trajectory or planner-answer imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.runtime.goal_grounding import GoalSpec
from src.runtime.action_semantics import ActionSpec, parse_action

PENDING = "PENDING"
ACTIVE = "ACTIVE"
SATISFIED = "SATISFIED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"


@dataclass
class Subgoal:
    kind: str
    target: str = ""
    status: str = PENDING
    evidence: List[str] = field(default_factory=list)

    def to_dict(self):
        return {"kind": self.kind, "target": self.target,
                "status": self.status, "evidence": list(self.evidence)}


# Generic task-relation templates (no concrete locations)
_FAMILY_SUBGOALS = {
    "look_at_obj_in_light": [
        ("EXPLORE", ""),
        ("LOCATE_TARGET", "{object}"),
        ("ACQUIRE_TARGET", "{object}"),
        ("LOCATE_TOOL", "{tool}"),
        ("USE_TOOL", "{tool}"),
        ("VERIFY_SUCCESS", "{object}"),
    ],
    "pick_and_place_simple": [
        ("EXPLORE", ""),
        ("LOCATE_TARGET", "{object}"),
        ("ACQUIRE_TARGET", "{object}"),
        ("LOCATE_DEST", "{receptacle}"),
        ("PLACE_TARGET", "{object}"),
        ("VERIFY_SUCCESS", "{object}"),
    ],
}


class ExplorationLog:
    """Visit record: visited ≠ exhaustively searched."""

    def __init__(self):
        self.visited: List[str] = []
        self.inspected_no_target: List[str] = []
        self.found_target_at: Optional[str] = None
        self.unexplored_visible: List[str] = []

    def visit(self, loc: str):
        loc = (loc or "").lower()
        if loc and loc not in self.visited:
            self.visited.append(loc)

    def mark_inspected_empty(self, loc: str):
        loc = (loc or "").lower()
        if loc and loc not in self.inspected_no_target:
            self.inspected_no_target.append(loc)

    def summary(self):
        return {
            "visited": list(self.visited),
            "inspected_no_target": list(self.inspected_no_target),
            "found_target_at": self.found_target_at,
            "unexplored_visible": list(self.unexplored_visible),
        }


class SubgoalPlanner:
    """Maintains an active subgoal stack driven by environment evidence."""

    def __init__(self, goal_spec: GoalSpec):
        self.goal_spec = goal_spec
        self.exploration = ExplorationLog()
        self.world_facts: Dict[str, Any] = {}
        self.held: List[str] = []
        self.subgoals: List[Subgoal] = self._build_subgoals(goal_spec)
        self.transition_log: List[Dict[str, Any]] = []

    def _build_subgoals(self, g: GoalSpec) -> List[Subgoal]:
        fam = g.task_family if g.task_family in _FAMILY_SUBGOALS else "pick_and_place_simple"
        out = []
        for kind, tgt in _FAMILY_SUBGOALS[fam]:
            t = tgt.format(
                object=g.target_object if g.target_object != "UNKNOWN" else "?",
                tool=g.target_receptacle if g.target_receptacle != "UNKNOWN" else "?",
                receptacle=g.target_receptacle if g.target_receptacle != "UNKNOWN" else "?",
            )
            out.append(Subgoal(kind=kind, target=t if t != "?" else ""))
        return out

    def active_subgoal(self) -> Optional[Subgoal]:
        for s in self.subgoals:
            if s.status in (PENDING, ACTIVE):
                return s
        return None

    def _set_status(self, sg: Subgoal, status: str, evidence: str):
        prev = sg.status
        sg.status = status
        if evidence and evidence not in sg.evidence:
            sg.evidence.append(evidence[:160])
        self.transition_log.append({"kind": sg.kind, "from": prev, "to": status,
                                    "evidence": evidence[:120]})

    def update_from_feedback(self, action_raw: str, obs_before: str, obs_after: str,
                             admissible=None) -> Optional[Subgoal]:
        """Advance/revise subgoals from env feedback. Returns new active subgoal."""
        act = parse_action(action_raw)
        after = (obs_after or "").lower()
        before = (obs_before or "").lower()
        g = self.goal_spec
        obj = (g.target_object or "").lower()
        obj_key = obj.replace(" ", "")
        tool = (g.target_receptacle or "").lower().replace(" ", "")
        sg = self.active_subgoal()

        # location tracking
        if act.action_type == "NAVIGATE" and act.target:
            self.exploration.visit(act.target)
        for loc in self.exploration.visited:
            if loc and loc in after:
                self.exploration.visit(loc)

        # object discovery via feedback (not goal text)
        discovered = False
        if obj_key and obj_key.replace(" ", "") in after.replace(" ", ""):
            if any(w in after for w in ("you see", "there is", "on the", "in the", "you arrive")):
                discovered = True
                self.world_facts[f"{obj_key}_seen"] = True
                self.exploration.found_target_at = self.exploration.visited[-1] if self.exploration.visited else None

        # pickup confirmation
        if act.action_type == "PICKUP":
            if "you pick up" in after and obj_key and obj_key.replace(" ", "") in after.replace(" ", ""):
                if obj not in self.held:
                    self.held.append(g.target_object)
                self.world_facts[f"{obj_key}_held"] = True
            elif any(w in after for w in ("can't", "cannot", "unable", "nothing happens")):
                self.world_facts[f"{obj_key}_held"] = False

        # release / place
        if act.action_type == "PLACE":
            if obj in self.held:
                self.held.remove(obj)
            self.world_facts[f"{obj_key}_held"] = False
            if any(w in after for w in ("you move", "you put", "you place")):
                self.world_facts[f"{obj_key}_placed"] = True

        # tool / light
        if act.action_type == "USE_TOOL":
            if "turn on" in after or "turning on" in after:
                self.world_facts["light_on"] = True
            elif "already" in after and "on" in after:
                self.world_facts["light_on"] = True
            else:
                self.world_facts.setdefault("light_on", UNKNOWN)

        # subgoal completion rules (evidence-based)
        if sg is None:
            return None
        k = sg.kind
        if k == "EXPLORE":
            if discovered or len(self.exploration.visited) >= 1:
                self._set_status(sg, SATISFIED, f"explore: visited={self.exploration.visited[-1] if self.exploration.visited else ''}")
        elif k == "LOCATE_TARGET":
            if discovered:
                self._set_status(sg, SATISFIED, f"discovered {g.target_object}")
        elif k == "ACQUIRE_TARGET":
            if self.world_facts.get(f"{obj_key}_held") is True:
                self._set_status(sg, SATISFIED, f"holding {g.target_object}")
            elif self.world_facts.get(f"{obj_key}_held") is False and act.action_type == "PICKUP":
                self._set_status(sg, BLOCKED, f"pickup failed: {after[:60]}")
        elif k in ("LOCATE_TOOL", "LOCATE_DEST"):
            if (act.target or "") and (tool in (act.target or "").replace(" ", "") or (g.target_receptacle or "").lower() in (act.target or "").lower()):
                self._set_status(sg, SATISFIED, f"reached {act.target}")
            elif k == "LOCATE_DEST" and g.target_receptacle and g.target_receptacle.lower() in after:
                self._set_status(sg, SATISFIED, f"visible {g.target_receptacle}")
        elif k == "USE_TOOL":
            if self.world_facts.get("light_on") is True:
                self._set_status(sg, SATISFIED, "light on confirmed")
            elif act.action_type == "USE_TOOL" and self.world_facts.get("light_on") == UNKNOWN:
                self._set_status(sg, ACTIVE, "use sent, unconfirmed")
        elif k == "PLACE_TARGET":
            if self.world_facts.get(f"{obj_key}_placed") is True:
                self._set_status(sg, SATISFIED, "placement confirmed")
            elif self.world_facts.get(f"{obj_key}_held") is False and act.action_type != "PLACE":
                self._set_status(sg, ACTIVE, "not holding")
        elif k == "VERIFY_SUCCESS":
            # only env won can satisfy; otherwise stays pending/active
            if self.world_facts.get("native_won") is True:
                self._set_status(sg, SATISFIED, "native won")

        # blocked → re-open as pending to allow retry
        if sg.status == BLOCKED:
            sg.status = PENDING

        return self.active_subgoal()

    def mark_native_won(self, won: bool):
        self.world_facts["native_won"] = bool(won)
        if won:
            for s in self.subgoals:
                if s.status in (PENDING, ACTIVE):
                    self._set_status(s, SATISFIED, "native won")

    def prompt_block(self, admissible=None) -> str:
        """Structured subgoal + grounded legal candidates for the LLM."""
        sg = self.active_subgoal()
        lines = ["Active Subgoal:"]
        if sg:
            lines.append(f"- kind={sg.kind} target={sg.target or '(n/a)'} status={sg.status}")
        else:
            lines.append("- none (all satisfied or blocked)")
        lines.append("Current World Facts:")
        if self.held:
            lines.append(f"- holding: {', '.join(self.held)}")
        for k, v in sorted(self.world_facts.items()):
            if k != "native_won":
                lines.append(f"- {k}: {v}")
        exp = self.exploration.summary()
        lines.append(
            f"- visited_locations={exp['visited'][:8]}; "
            f"found_target_at={exp['found_target_at']}"
        )
        from src.runtime.action_semantics import relevant_candidates

        cands = relevant_candidates(admissible or [], self.goal_spec, sg)
        if cands:
            lines.append("Legal Action Candidates related to subgoal:")
            for s in cands[:8]:
                lines.append(f"- {s.raw_command}  [{s.action_type}]")
        return "\n".join(lines)
