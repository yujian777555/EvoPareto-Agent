"""Structural mutation operators for WorkflowGenome (Stage 2.0).

Real structure edits — not config strings. Each operator can fail (return
None) if the edit would break validity.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from src.research.fceol.workflow_genome import (
    DIAGNOSE,
    GENERATE,
    REPAIR,
    ROUTE,
    SUBMIT,
    VERIFY,
    GenomeInvalid,
    Node,
    WorkflowGenome,
)

M_INSERT_VERIFICATION = "M1_INSERT_VERIFICATION"
M_ADD_FAILURE_RECOVERY = "M2_ADD_FAILURE_RECOVERY"
M_CHANGE_TOOL_ROUTING = "M3_CHANGE_TOOL_ROUTING"
M_MODIFY_CONTEXT_FLOW = "M4_MODIFY_CONTEXT_FLOW"

MUTATION_OPERATORS = (
    M_INSERT_VERIFICATION,
    M_ADD_FAILURE_RECOVERY,
    M_CHANGE_TOOL_ROUTING,
    M_MODIFY_CONTEXT_FLOW,
)


def _try(g: WorkflowGenome) -> Optional[WorkflowGenome]:
    try:
        g.validate()
        return g
    except GenomeInvalid:
        return None


def m1_insert_verification(g: WorkflowGenome) -> Optional[WorkflowGenome]:
    """GENERATE → VERIFY → (SUBMIT|REPAIR). Adds real verification step."""
    c = g.clone()
    if any(n.kind == VERIFY for n in c.nodes):
        # enable instead of duplicating
        for n in c.nodes:
            if n.kind == VERIFY:
                n.enabled = True
        return _try(c)
    vid = "n_ver"
    if c.node(vid):
        vid = "n_ver2"
    c.nodes.append(Node(vid, VERIFY))
    # rewire: GENERATE -> VERIFY -> old successors of GENERATE
    new_edges = []
    for a, b in c.edges:
        if any(n.node_id == a and n.kind == GENERATE for n in c.nodes):
            new_edges.append((a, vid))
            new_edges.append((vid, b))
        else:
            new_edges.append((a, b))
    c.edges = new_edges
    return _try(c)


def m2_add_failure_recovery(g: WorkflowGenome) -> Optional[WorkflowGenome]:
    """Add DIAGNOSE → REPAIR loop back to GENERATE, bounded by max_repairs."""
    c = g.clone()
    if any(n.kind == REPAIR for n in c.nodes):
        for n in c.nodes:
            if n.kind in (DIAGNOSE, REPAIR):
                n.enabled = True
        c.max_repairs = max(c.max_repairs, 1)
        return _try(c)
    c.nodes.append(Node("n_diag", DIAGNOSE))
    c.nodes.append(Node("n_rep", REPAIR))
    # find a verify-or-generate to hang recovery from
    src = None
    for n in c.nodes:
        if n.kind == VERIFY and n.enabled:
            src = n.node_id
            break
    if src is None:
        src = "n_gen"
    c.edges.append((src, "n_diag"))
    c.edges.append(("n_diag", "n_rep"))
    c.edges.append(("n_rep", "n_gen"))
    c.max_repairs = min(3, max(c.max_repairs, 1) + 1)
    return _try(c)


def m3_change_tool_routing(g: WorkflowGenome) -> Optional[WorkflowGenome]:
    """Toggle route_policy and optionally insert ROUTE node."""
    c = g.clone()
    c.route_policy = "verify_first" if c.route_policy == "direct" else "direct"
    if not any(n.kind == ROUTE for n in c.nodes):
        c.nodes.append(Node("n_route", ROUTE, params={"policy": c.route_policy}))
        c.edges.append(("n_gen", "n_route"))
    else:
        for n in c.nodes:
            if n.kind == ROUTE:
                n.params["policy"] = c.route_policy
    return _try(c)


def m4_modify_context_flow(g: WorkflowGenome) -> Optional[WorkflowGenome]:
    """Change context_mode cycle: full → truncated → none → full."""
    c = g.clone()
    order = ("full", "truncated", "none")
    i = order.index(c.context_mode) if c.context_mode in order else 0
    c.context_mode = order[(i + 1) % len(order)]
    return _try(c)


OPERATOR_FNS: Dict[str, Callable[[WorkflowGenome], Optional[WorkflowGenome]]] = {
    M_INSERT_VERIFICATION: m1_insert_verification,
    M_ADD_FAILURE_RECOVERY: m2_add_failure_recovery,
    M_CHANGE_TOOL_ROUTING: m3_change_tool_routing,
    M_MODIFY_CONTEXT_FLOW: m4_modify_context_flow,
}


def apply_operator(name: str, g: WorkflowGenome) -> Optional[WorkflowGenome]:
    fn = OPERATOR_FNS.get(name)
    if fn is None:
        return None
    return fn(g)
