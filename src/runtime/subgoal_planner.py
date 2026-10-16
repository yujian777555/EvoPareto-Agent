"""Evidence-driven subgoal planner (Stage 1.7-R1).

P0 fixes:
- reset_for_goal(): full rebuild on goal change (no stale subgoals).
- UNKNOWN family → UNSUPPORTED_GOAL (never fake pick_and_place).
- Consistent world-fact reconciliation (early facts satisfy later subgoals).
- EXPLORE is not complete after a single visit.
- Failed pickup / unconfirmed place never flip hold/place facts.
- Tool located when a matching use action is actually available/confirmed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.runtime.goal_grounding import UNKNOWN as GOAL_UNKNOWN
from src.runtime.goal_grounding import GoalSpec
from src.runtime.action_semantics import parse_action

PENDING = "PENDING"
ACTIVE = "ACTIVE"
SATISFIED = "SATISFIED"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"
UNSUPPORTED = "UNSUPPORTED_GOAL"

# Exploration phases (D1)
VISITED_UNINSPECTED = "VISITED_UNINSPECTED"
INSPECTED_NO_TARGET = "INSPECTED_NO_TARGET"
TARGET_FOUND = "TARGET_FOUND"


@dataclass
class Subgoal:
    kind: str
    target: str = ""
    status: str = PENDING
    evidence: List[str] = field(default_factory=list)

    def to_dict(self):
        return {"kind": self.kind, "target": self.target,
                "status": self.status, "evidence": list(self.evidence)}


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
    """visited ≠ inspected; empty container ≠ forever target-free."""

    def __init__(self):
        self.locations: Dict[str, str] = {}  # loc -> phase
        self.found_target_at: Optional[str] = None

    def visit(self, loc: str):
        loc = (loc or "").lower().strip()
        if not loc:
            return
        if loc not in self.locations:
            self.locations[loc] = VISITED_UNINSPECTED

    def inspect(self, loc: str, *, found_target: bool = False):
        loc = (loc or "").lower().strip()
        if not loc:
            return
        self.visit(loc)
        if found_target:
            self.locations[loc] = TARGET_FOUND
            self.found_target_at = loc
        elif self.locations.get(loc) != TARGET_FOUND:
            self.locations[loc] = INSPECTED_NO_TARGET

    def unvisited(self, visible_locs):
        return [v for v in visible_locs if v.lower().strip() not in self.locations]

    def incompletely_inspected(self):
        return [k for k, v in self.locations.items() if v == VISITED_UNINSPECTED]

    def exhausted(self, visible_locs) -> bool:
        """True only if every visible location is inspected with no target."""
        vis = [v.lower().strip() for v in visible_locs]
        if not vis:
            return False
        return all(self.locations.get(v) == INSPECTED_NO_TARGET for v in vis)

    def summary(self):
        return {
            "locations": dict(self.locations),
            "found_target_at": self.found_target_at,
            "incompletely_inspected": self.incompletely_inspected(),
        }


class SubgoalPlanner:
    def __init__(self, goal_spec: Optional[GoalSpec] = None):
        self.goal_spec = goal_spec or GoalSpec()
        self.exploration = ExplorationLog()
        self.world_facts: Dict[str, Any] = {}
        self.held: List[str] = []
        self.subgoals: List[Subgoal] = []
        self.transition_log: List[Dict[str, Any]] = []
        self._task_fingerprint = ""
        self._build(self.goal_spec)

    # ---- A1/A2: correct initialization / reset ----
    def reset_for_goal(self, goal_spec: GoalSpec) -> None:
        """Full rebuild. Safe to call on every episode start or goal change."""
        self.goal_spec = goal_spec
        self.exploration = ExplorationLog()
        self.world_facts = {}
        self.held = []
        self.transition_log = []
        self._build(goal_spec)

    def _fingerprint(self, g: GoalSpec) -> str:
        return f"{g.task_family}|{g.target_object}|{g.target_receptacle}|{g.required_relation}"

    def _build(self, g: GoalSpec) -> None:
        self._task_fingerprint = self._fingerprint(g)
        fam = g.task_family
        if fam not in _FAMILY_SUBGOALS:
            # A2: never pretend it is pick_and_place
            self.subgoals = [Subgoal(kind=UNSUPPORTED, target="", status=BLOCKED,
                                     evidence=[f"unsupported family={fam}"])]
            return
        out = []
        obj = g.target_object if g.target_object not in (GOAL_UNKNOWN, "") else "?"
        tool = g.target_receptacle if g.target_receptacle not in (GOAL_UNKNOWN, "") else "?"
        recep = tool
        for kind, tmpl in _FAMILY_SUBGOALS[fam]:
            t = tmpl.format(object=obj, tool=tool, receptacle=recep)
            out.append(Subgoal(kind=kind, target="" if t == "?" else t))
        self.subgoals = out

    def ensure_goal(self, goal_spec: GoalSpec) -> None:
        """Rebuild only when the task actually changes (keep episode progress)."""
        fp = self._fingerprint(goal_spec)
        if fp != self._task_fingerprint:
            self.reset_for_goal(goal_spec)

    def active_subgoal(self) -> Optional[Subgoal]:
        for s in self.subgoals:
            if s.status in (PENDING, ACTIVE, BLOCKED):
                # BLOCKED retryable → acts as active until SATISFIED
                return s
        return None

    def _set_status(self, sg: Subgoal, status: str, evidence: str):
        prev = sg.status
        if prev == status:
            return
        sg.status = status
        if evidence and evidence not in sg.evidence:
            sg.evidence.append(evidence[:160])
        self.transition_log.append({"kind": sg.kind, "from": prev, "to": status,
                                    "evidence": evidence[:120]})

    # ---- B1/A3: consistent reconciliation from world facts ----
    def _reconcile(self) -> None:
        """Satisfy or REOPEN subgoals from confirmed current facts.

        SATISFIED is not monotonic: release / wrong-place reopens later steps.
        Never uses unconfirmed guesses.
        """
        g = self.goal_spec
        obj = (g.target_object or "").lower()
        obj_key = obj.replace(" ", "")
        tool = (g.target_receptacle or "").lower().replace(" ", "")
        held = any(obj and obj in h.lower().replace(" ", "") for h in self.held) or \
            self.world_facts.get(f"{obj_key}_held") is True
        ever_discovered = (
            self.world_facts.get(f"{obj_key}_seen") is True
            or self.exploration.found_target_at is not None
        )
        discovered = ever_discovered or held
        light_on = self.world_facts.get("light_on") is True
        goal_placed = self.world_facts.get("goal_placement_satisfied") is True
        physical_release = self.world_facts.get("object_released") is True
        tool_visible = self.world_facts.get(f"{tool}_visible") is True if tool else False

        for sg in self.subgoals:
            k = sg.kind
            # A3: allow reopening SATISFIED when current preconditions fail
            if sg.status == SATISFIED:
                if k == "ACQUIRE_TARGET" and not held and not goal_placed and (
                    physical_release or self.world_facts.get(f"{obj_key}_held") is False
                ):
                    self._set_status(sg, PENDING, "reopen: no longer holding target")
                elif k == "PLACE_TARGET" and not goal_placed and physical_release:
                    self._set_status(sg, PENDING, "reopen: wrong/incomplete placement")
                elif k == "USE_TOOL" and not light_on and self.world_facts.get("light_on") is False:
                    self._set_status(sg, PENDING, "reopen: light not on")
                continue
            if k == "EXPLORE":
                if discovered:
                    self._set_status(sg, SATISFIED, "explore: target evidence present")
            elif k == "LOCATE_TARGET":
                if discovered:
                    self._set_status(sg, SATISFIED, f"discovered {g.target_object}")
            elif k == "ACQUIRE_TARGET":
                if held:
                    self._set_status(sg, SATISFIED, f"holding {g.target_object}")
            elif k == "LOCATE_TOOL":
                if light_on or tool_visible or self._tool_use_available():
                    self._set_status(sg, SATISFIED, "tool visible/usable")
            elif k == "LOCATE_DEST":
                if self.world_facts.get(f"{(g.target_receptacle or '').lower().replace(' ','')}_visible") is True:
                    self._set_status(sg, SATISFIED, "destination visible")
                elif goal_placed:
                    self._set_status(sg, SATISFIED, "already placed")
            elif k == "USE_TOOL":
                if light_on:
                    self._set_status(sg, SATISFIED, "light on confirmed")
            elif k == "PLACE_TARGET":
                if goal_placed:
                    self._set_status(sg, SATISFIED, "goal placement confirmed")
            elif k == "VERIFY_SUCCESS":
                if self.world_facts.get("native_won") is True:
                    self._set_status(sg, SATISFIED, "native won")

        if self.world_facts.get(f"{obj_key}_held") is True and goal_placed:
            self.world_facts[f"{obj_key}_held"] = UNKNOWN

    def _tool_use_available(self) -> bool:
        return bool(self.world_facts.get("_use_tool_action_available"))

    def update_from_feedback(self, action_raw: str, obs_before: str, obs_after: str,
                             admissible=None) -> Optional[Subgoal]:
        act = parse_action(action_raw)
        after = (obs_after or "").lower()
        g = self.goal_spec
        obj = (g.target_object or "").lower()
        obj_key = obj.replace(" ", "")
        tool = (g.target_receptacle or "").lower().replace(" ", "")
        dest = (g.target_receptacle or "").lower().replace(" ", "")

        # exploration tracking
        if act.action_type == "NAVIGATE" and act.target:
            self.exploration.visit(act.target)
        # inspect evidence
        if obj_key and obj_key.replace(" ", "") in after.replace(" ", ""):
            if any(w in after for w in ("you see", "there is", "on the", "in the", "you arrive")):
                self.world_facts[f"{obj_key}_seen"] = True
                loc = act.target if act.action_type == "NAVIGATE" else (
                    self.exploration.found_target_at or ""
                )
                self.exploration.inspect(loc or "current", found_target=True)

        # C1: tool visible/usable when a use <tool> action exists
        if admissible:
            use_ok = any(
                a.lower().startswith("use ") and tool and tool in a.lower().replace(" ", "")
                for a in admissible
            )
            self.world_facts["_use_tool_action_available"] = use_ok
            if use_ok:
                self.world_facts[f"{tool}_visible"] = True

        # pickup (B3): feedback phrase is authoritative even if action name differs
        if "you pick up" in after:
            import re as _re
            m = _re.search(r"you pick up the (.+?)(?: from |\.|$)", after)
            name = (m.group(1).strip().rstrip(".") if m else act.object or "")
            if name and name not in self.held:
                self.held.append(name)
            nk = name.lower().replace(" ", "")
            if nk:
                self.world_facts[f"{nk}_held"] = True
            if obj_key and (obj_key in nk or nk in obj_key or obj_key in after.replace(" ", "")):
                self.world_facts[f"{obj_key}_held"] = True
                self.world_facts[f"{obj_key}_seen"] = True
        elif act.action_type == "PICKUP":
            obj_cmd = (act.object or "").lower().replace(" ", "")
            if "you pick up" in after:
                name = act.object or ""
                if obj_key and (obj_key in after.replace(" ", "") or obj_key in obj_cmd):
                    if name and name not in self.held:
                        self.held.append(name)
                    self.world_facts[f"{obj_key}_held"] = True
                    self.world_facts[f"{obj_key}_seen"] = True
                elif name and name not in self.held:
                    self.held.append(name)  # picked some object (record as held)
            elif any(w in after for w in ("can't", "cannot", "unable", "nothing happens", "there is no")):
                # failed pickup: do NOT set held; do NOT clear other holds
                if obj_key:
                    self.world_facts[f"{obj_key}_held"] = False

        # place (A1): physical release ≠ goal placement
        if act.action_type == "PLACE":
            obj_cmd = (act.object or "").lower().replace(" ", "")
            tgt_cmd = (act.target or "").lower().replace(" ", "")
            confirmed = any(w in after for w in ("you move", "you put", "you place", "you drop"))
            obj_match = bool(obj_key) and (
                obj_key in obj_cmd or obj_key in after.replace(" ", "") or obj_cmd in obj_key
            )
            dest_match = bool(dest) and (
                dest in tgt_cmd or dest in after.replace(" ", "") or tgt_cmd in dest
            )
            if confirmed:
                # physical release always on confirmed place
                if act.object and act.object in self.held:
                    self.held.remove(act.object)
                elif obj:
                    self.held = [h for h in self.held if obj not in h.lower()]
                self.world_facts[f"{obj_key}_held"] = False
                self.world_facts["object_released"] = True
                self.world_facts[f"{obj_key}_released"] = True
                if act.target:
                    self.world_facts[f"{tgt_cmd}_visible"] = True
                # goal placement ONLY if object AND destination match GoalSpec
                if obj_match and dest_match and g.required_relation in ("in", "on", "to", UNKNOWN, ""):
                    self.world_facts["goal_placement_satisfied"] = True
                    self.world_facts[f"{obj_key}_placed"] = True
                    self.world_facts[f"{obj_key}_placed_at"] = act.target
                else:
                    # wrong object or wrong destination: released but goal NOT satisfied
                    self.world_facts["goal_placement_satisfied"] = False
                    self.world_facts[f"{obj_key}_placed"] = False
                    self.world_facts[f"{obj_key}_placed_wrong"] = act.target or act.object
            else:
                if self.world_facts.get(f"{obj_key}_held") is True:
                    self.world_facts[f"{obj_key}_held"] = UNKNOWN

        # tool use
        if act.action_type == "USE_TOOL":
            if "turn on" in after or "turning on" in after or "already" in after and "on" in after:
                self.world_facts["light_on"] = True
            else:
                self.world_facts.setdefault("light_on", UNKNOWN)

        # destination visibility
        if act.action_type == "NAVIGATE" and dest and dest in (act.target or "").replace(" ", ""):
            self.world_facts[f"{dest}_visible"] = True

        # failed action should not advance a subgoal via action-name alone
        if act.action_type == "PICKUP" and "you pick up" not in after:
            pass

        self._reconcile()
        return self.active_subgoal()

    def mark_native_won(self, won: bool):
        self.world_facts["native_won"] = bool(won)
        self._reconcile()
        if won:
            for s in self.subgoals:
                if s.status not in (SATISFIED,):
                    self._set_status(s, SATISFIED, "native won")

    def prompt_block(self, admissible=None) -> str:
        sg = self.active_subgoal()
        lines = ["Active Subgoal:"]
        if sg:
            lines.append(f"- kind={sg.kind} target={sg.target or '(n/a)'} status={sg.status}")
        else:
            lines.append("- none (all satisfied or blocked)")
        if self.subgoals and self.subgoals[0].kind == UNSUPPORTED:
            lines.append("- UNSUPPORTED_GOAL: cannot build a grounded plan for this goal text")
        lines.append("Current World Facts:")
        if self.held:
            lines.append(f"- holding: {', '.join(self.held)}")
        for k, v in sorted(self.world_facts.items()):
            if k != "native_won" and not k.startswith("_"):
                lines.append(f"- {k}: {v}")
        exp = self.exploration.summary()
        lines.append(f"- exploration={exp}")
        from src.runtime.action_semantics import relevant_candidates

        cands = relevant_candidates(admissible or [], self.goal_spec, sg,
                                    held_objects=self.held)
        if cands:
            lines.append("Legal Action Candidates related to subgoal:")
            for s in cands[:12]:
                lines.append(f"- {s.raw_command}  [{s.action_type}]")
        elif admissible is not None and len(admissible) == 0:
            lines.append("GROUNDING_BLOCKED: no legal actions")
        return "\n".join(lines)
