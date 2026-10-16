"""Deterministic executable workflow interpreter (P0-2).

Each node reads/writes real execution state. Reward comes from the
INDEPENDENT evaluator checking the submitted artifact against the task's
required_checks — never from a fault_type lookup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.research.fceol.workflow_genome import (
    DIAGNOSE,
    GENERATE,
    REPAIR,
    ROUTE,
    SUBMIT,
    VERIFY,
    WorkflowGenome,
)
from src.research.fceol_r1.task_suite import TaskInstance

# Observable symptoms
SYM_WRONG_OUTPUT = "wrong_output_submitted"
SYM_NO_VERIFY = "no_verification_performed"
SYM_REPAIR_STUCK = "repair_without_improvement"
SYM_TOOL_MISUSE = "tool_misuse_detected"
SYM_CONSTRAINT_LOST = "constraint_lost"
SYM_PARTIAL = "partial_solution"
SYM_OK = "clean_run"


@dataclass
class ExecutionState:
    task: TaskInstance
    candidate_quality: float = 0.0
    constraint_present: bool = True
    tool_used: str = ""
    tool_correct: bool = False
    verified_ok: bool = False
    verify_feedback: str = ""
    diagnosis: str = ""
    repaired: bool = False
    submitted: bool = False
    # fault-injection channels (set by env, not read by policy)
    tool_is_broken: bool = False
    verifier_sabotaged: bool = False
    context_dropped: bool = False
    recovery_miswired: bool = False
    events: List[Dict[str, Any]] = field(default_factory=list)
    symptoms: List[str] = field(default_factory=list)

    def log(self, node_id: str, node_type: str, in_state: Dict[str, Any], out_state: Dict[str, Any], kind: str = "execution_event"):
        self.events.append({
            "node_id": node_id, "node_type": node_type, "kind": kind,
            "input_state": dict(in_state), "output_state": dict(out_state),
        })


class WorkflowInterpreter:
    """Runs a WorkflowGenome against a TaskInstance + injected fault channels."""

    def __init__(self, genome: WorkflowGenome, *, max_events: int = 40):
        self.genome = genome
        self.max_events = max_events

    def _nodes_by_kind(self, kind: str):
        return [n for n in self.genome.nodes if n.kind == kind and n.enabled]

    def _next_after(self, node_id: str) -> List[str]:
        return [b for a, b in self.genome.edges if a == node_id]

    def run(self, task: TaskInstance, fault_channels: Dict[str, bool]) -> Tuple[ExecutionState, float]:
        st = ExecutionState(
            task=task,
            tool_is_broken=bool(fault_channels.get("tool_is_broken", False)),
            verifier_sabotaged=bool(fault_channels.get("verifier_sabotaged", False)),
            context_dropped=bool(fault_channels.get("context_dropped", False)),
            recovery_miswired=bool(fault_channels.get("recovery_miswired", False)),
        )
        # genome context_mode interacts with context_dropped fault
        cm = self.genome.context_mode
        if st.context_dropped:
            if cm == "truncated":
                # fallback re-derivation of constraint partially compensates
                st.constraint_present = True
                st.candidate_quality = 0.0  # will be set by GENERATE, minus penalty later
                st.symptoms.append(SYM_CONSTRAINT_LOST)
            else:
                st.constraint_present = False
                st.symptoms.append(SYM_CONSTRAINT_LOST)
        elif cm == "none":
            st.constraint_present = False
            st.symptoms.append(SYM_CONSTRAINT_LOST)

        # genome route_policy seed
        if self.genome.route_policy == "verify_first":
            st.tool_used = task.correct_tool
            st.tool_correct = True

        # --- GENERATE ---
        gens = self._nodes_by_kind(GENERATE)
        if not gens:
            st.symptoms.append(SYM_WRONG_OUTPUT)
            return st, 0.0
        g0 = gens[0]
        q = task.base_output_quality
        if not st.constraint_present:
            q *= 0.5
        st.candidate_quality = q
        st.log(g0.node_id, GENERATE, {"q_in": 0.0, "constraint": st.constraint_present},
               {"q_out": q, "constraint": st.constraint_present})

        used = {GENERATE}
        # walk from GENERATE along enabled edges, bounded
        frontier = self._next_after(g0.node_id)
        repairs_left = self.genome.max_repairs
        steps = 0
        while frontier and steps < self.max_events:
            steps += 1
            nid = frontier.pop(0)
            node = self.genome.node(nid)
            if node is None or not node.enabled:
                continue
            # prevent infinite loop on same node
            if node.kind != REPAIR and nid in used and node.kind != ROUTE:
                continue
            used.add(nid)

            if node.kind == ROUTE:
                self._exec_route(st, node.node_id, node.params)
                frontier.extend(self._next_after(nid))
            elif node.kind == VERIFY:
                self._exec_verify(st, node.node_id)
                if not st.verified_ok:
                    # go through DIAGNOSE if present, else REPAIR
                    diags = self._nodes_by_kind(DIAGNOSE)
                    rec = self._nodes_by_kind(REPAIR)
                    if diags:
                        frontier = [diags[0].node_id]
                    elif rec and repairs_left > 0:
                        frontier = [rec[0].node_id]
                    else:
                        frontier.extend(self._next_after(nid))
                else:
                    frontier.extend(self._next_after(nid))
            elif node.kind == DIAGNOSE:
                self._exec_diagnose(st, node.node_id)
                frontier.extend(self._next_after(nid))
            elif node.kind == REPAIR:
                if repairs_left <= 0:
                    frontier.extend(self._next_after(nid))
                    continue
                repairs_left -= 1
                self._exec_repair(st, node.node_id)
                frontier.extend(self._next_after(nid))
            elif node.kind == SUBMIT:
                self._exec_submit(st, node.node_id)
                break
            else:
                frontier.extend(self._next_after(nid))

        if not st.submitted:
            st.symptoms.append(SYM_WRONG_OUTPUT)

        reward = self.independent_evaluate(st)
        return st, reward

    # ---- node semantics ----
    def _exec_route(self, st: ExecutionState, nid: str, params: Dict[str, Any]):
        before = {"q": st.candidate_quality, "tool": st.tool_used}
        policy = self.genome.route_policy or params.get("policy", "direct")
        if policy == "verify_first":
            st.tool_used = st.task.correct_tool
            st.tool_correct = True
        else:
            st.tool_used = st.task.tool_catalog[0]
            st.tool_correct = (st.tool_used == st.task.correct_tool)
        if st.tool_is_broken or not st.tool_correct:
            st.candidate_quality *= 0.7
            if SYM_TOOL_MISUSE not in st.symptoms:
                st.symptoms.append(SYM_TOOL_MISUSE)
        else:
            st.candidate_quality = min(1.0, st.candidate_quality + 0.15)
        st.log(nid, ROUTE, before, {"q": st.candidate_quality, "tool": st.tool_used, "correct": st.tool_correct})

    def _exec_verify(self, st: ExecutionState, nid: str):
        before = {"q": st.candidate_quality, "feedback": ""}
        if st.verifier_sabotaged:
            # broken verifier always claims OK
            st.verified_ok = True
            st.verify_feedback = "false_pass"
            st.symptoms.append(SYM_WRONG_OUTPUT)
        else:
            ok = st.candidate_quality >= 0.55 and st.constraint_present
            st.verified_ok = ok
            st.verify_feedback = "pass" if ok else "fail:quality_or_constraint"
            if not ok:
                st.symptoms.append(SYM_NO_VERIFY if False else SYM_PARTIAL)
        st.log(nid, VERIFY, before, {"verified_ok": st.verified_ok, "feedback": st.verify_feedback})

    def _exec_diagnose(self, st: ExecutionState, nid: str):
        before = {"feedback": st.verify_feedback, "q": st.candidate_quality}
        if st.verify_feedback.startswith("fail"):
            if not st.constraint_present:
                st.diagnosis = "constraint_missing"
            elif not st.tool_correct:
                st.diagnosis = "wrong_tool"
            else:
                st.diagnosis = "low_quality"
        elif st.verify_feedback == "false_pass":
            # verifier lied; diagnose notices inconsistency with symptoms
            st.diagnosis = "low_quality" if st.candidate_quality < 0.55 else "ok"
        elif st.tool_correct is False:
            st.diagnosis = "wrong_tool"
        elif not st.constraint_present:
            st.diagnosis = "constraint_missing"
        elif st.candidate_quality < 0.55:
            st.diagnosis = "low_quality"
        else:
            st.diagnosis = "ok"
        st.log(nid, DIAGNOSE, before, {"diagnosis": st.diagnosis})

    def _exec_repair(self, st: ExecutionState, nid: str):
        before = {"q": st.candidate_quality, "diag": st.diagnosis}
        if st.recovery_miswired:
            st.candidate_quality *= 0.9
            st.symptoms.append(SYM_REPAIR_STUCK)
            st.repaired = True
            st.log(nid, REPAIR, before, {"q": st.candidate_quality}, kind="failure_event")
            return
        if st.diagnosis == "constraint_missing":
            st.constraint_present = True
            st.candidate_quality = min(1.0, st.candidate_quality + 0.55)
        elif st.diagnosis == "wrong_tool":
            st.tool_used = st.task.correct_tool
            st.tool_correct = True
            st.candidate_quality = min(1.0, st.candidate_quality + 0.5)
        elif st.diagnosis == "low_quality":
            st.candidate_quality = min(1.0, st.candidate_quality + 0.5)
        elif st.diagnosis == "insufficient_evidence":
            st.candidate_quality = min(1.0, st.candidate_quality + 0.2)
        st.repaired = True
        st.log(nid, REPAIR, before, {"q": st.candidate_quality})

    def _exec_submit(self, st: ExecutionState, nid: str):
        st.submitted = True
        st.log(nid, SUBMIT, {"q": st.candidate_quality},
               {"submitted": True, "constraint": st.constraint_present})

    def independent_evaluate(self, st: ExecutionState) -> float:
        """Reward = artifact quality vs task.required_checks. No fault lookup."""
        checks = st.task.required_checks
        score = 0.0
        q = min(1.0, st.candidate_quality)
        if "consistency" in checks:
            score += 0.5 * q
        if "completeness" in checks:
            score += 0.5 * q * (1.0 if st.constraint_present else 0.35)
        # small complexity cost so "enable everything" is not free
        n_on = sum(1 for n in self.genome.nodes if n.enabled)
        score -= 0.015 * max(0, n_on - 2)
        return round(max(0.0, score), 4)
