"""Executable workflow genome (Stage 2.0).

A small, validated agent-workflow structure — not arbitrary code, not prompt
labels. Nodes have real execution semantics in offline_evaluator.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Node kinds (executable)
GENERATE = "GENERATE"
VERIFY = "VERIFY"
DIAGNOSE = "DIAGNOSE"
REPAIR = "REPAIR"
ROUTE = "ROUTE"
SUBMIT = "SUBMIT"


@dataclass
class Node:
    node_id: str
    kind: str
    enabled: bool = True
    params: Dict[str, Any] = field(default_factory=dict)


class GenomeInvalid(ValueError):
    pass


@dataclass
class WorkflowGenome:
    nodes: List[Node] = field(default_factory=list)
    edges: List[tuple] = field(default_factory=list)  # (src_id, dst_id)
    max_repairs: int = 1
    context_mode: str = "full"  # full | truncated | none
    route_policy: str = "direct"  # direct | verify_first

    # ---- serialization ----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [
                {"node_id": n.node_id, "kind": n.kind, "enabled": n.enabled, "params": dict(n.params)}
                for n in self.nodes
            ],
            "edges": [list(e) for e in self.edges],
            "max_repairs": self.max_repairs,
            "context_mode": self.context_mode,
            "route_policy": self.route_policy,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorkflowGenome":
        return cls(
            nodes=[Node(n["node_id"], n["kind"], bool(n.get("enabled", True)), dict(n.get("params") or {}))
                   for n in d.get("nodes") or []],
            edges=[(e[0], e[1]) for e in d.get("edges") or []],
            max_repairs=int(d.get("max_repairs", 1)),
            context_mode=str(d.get("context_mode", "full")),
            route_policy=str(d.get("route_policy", "direct")),
        )

    def serialize(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def deserialize(cls, s: str) -> "WorkflowGenome":
        return cls.from_dict(json.loads(s))

    def hash(self) -> str:
        return hashlib.sha256(self.serialize().encode()).hexdigest()[:16]

    def clone(self) -> "WorkflowGenome":
        return WorkflowGenome.from_dict(self.to_dict())

    def enabled_kinds(self) -> Set[str]:
        return {n.kind for n in self.nodes if n.enabled}

    def node(self, node_id: str) -> Optional[Node]:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    # ---- validation ----
    def validate(self) -> None:
        ids = [n.node_id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise GenomeInvalid("duplicate node ids")
        if not any(n.kind == GENERATE for n in self.nodes):
            raise GenomeInvalid("missing GENERATE")
        if not any(n.kind == SUBMIT for n in self.nodes):
            raise GenomeInvalid("missing SUBMIT")
        idset = set(ids)
        for s, t in self.edges:
            if s not in idset or t not in idset:
                raise GenomeInvalid(f"edge {s}->{t} references missing node")
        # reachability from GENERATE to SUBMIT over enabled nodes
        start = [n.node_id for n in self.nodes if n.kind == GENERATE and n.enabled][0]
        goal = {n.node_id for n in self.nodes if n.kind == SUBMIT and n.enabled}
        seen = set()
        stack = [start]
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            for a, b in self.edges:
                if a == u and b in idset:
                    nd = self.node(b)
                    if nd and nd.enabled:
                        stack.append(b)
        if not (seen & goal):
            raise GenomeInvalid("SUBMIT unreachable from GENERATE")
        # no self-loop-only cycles that never reach submit: bounded by max_repairs
        if self.max_repairs < 0 or self.max_repairs > 3:
            raise GenomeInvalid("max_repairs out of range")
        if self.context_mode not in ("full", "truncated", "none"):
            raise GenomeInvalid("bad context_mode")
        if self.route_policy not in ("direct", "verify_first"):
            raise GenomeInvalid("bad route_policy")


def base_genome() -> WorkflowGenome:
    """Minimal legal workflow: GENERATE → SUBMIT."""
    g = WorkflowGenome(
        nodes=[Node("n_gen", GENERATE), Node("n_sub", SUBMIT)],
        edges=[("n_gen", "n_sub")],
        max_repairs=1,
        context_mode="full",
        route_policy="direct",
    )
    g.validate()
    return g
