"""FCEOL unit tests: genome, evidence, operators, policies, no-leakage."""
from __future__ import annotations

import random

import pytest

from src.research.fceol.controlled_faults import (
    FAULT_MISSING_VERIFY,
    FAULT_TOOL_ROUTING,
    ControlledEnv,
    make_task_suite,
    split_tasks,
)
from src.research.fceol.failure_evidence import (
    UNKNOWN,
    FailureEvidence,
    evidence_from_trace,
)
from src.research.fceol.intervention_credit import InterventionCredit, InterventionRecord
from src.research.fceol.mutation_operators import (
    M_ADD_FAILURE_RECOVERY,
    M_CHANGE_TOOL_ROUTING,
    M_INSERT_VERIFICATION,
    M_MODIFY_CONTEXT_FLOW,
    apply_operator,
)
from src.research.fceol.operator_policy import (
    FailureConditionedPolicy,
    GlobalAOS,
    RandomMutation,
    ShuffledFailurePolicy,
)
from src.research.fceol.workflow_genome import base_genome, GenomeInvalid


# ---- genome ----
def test_genome_serialize_roundtrip():
    g = base_genome()
    g2 = type(g).deserialize(g.serialize())
    assert g2.hash() == g.hash()
    g2.validate()


def test_mutations_produce_different_structure():
    g = base_genome()
    s0 = g.hash()
    for op in (M_INSERT_VERIFICATION, M_ADD_FAILURE_RECOVERY,
               M_CHANGE_TOOL_ROUTING, M_MODIFY_CONTEXT_FLOW):
        c = apply_operator(op, g)
        assert c is not None, op
        c.validate()
        assert c.hash() != s0 or op == M_MODIFY_CONTEXT_FLOW  # params change counts too
    m1 = apply_operator(M_INSERT_VERIFICATION, g)
    assert "VERIFY" in m1.enabled_kinds()
    m2 = apply_operator(M_ADD_FAILURE_RECOVERY, g)
    assert "REPAIR" in m2.enabled_kinds()
    m3 = apply_operator(M_CHANGE_TOOL_ROUTING, g)
    assert m3.route_policy != g.route_policy


def test_genome_validation_rejects_broken():
    g = base_genome()
    g.edges = []
    with pytest.raises(GenomeInvalid):
        g.validate()


# ---- failure evidence ----
def test_low_confidence_becomes_unknown():
    ev = evidence_from_trace(task_id="t", genome_id="g", symptoms=["wrong_output_passed"],
                             trace_ids=["x"], diagnosed_category="VERIFICATION_FAILURE", confidence=0.1)
    assert ev.failure_category == UNKNOWN
    assert ev.context_key() == "ctx:UNKNOWN"


def test_high_confidence_keeps_category():
    ev = evidence_from_trace(task_id="t", genome_id="g", symptoms=["wrong_output_passed"],
                             trace_ids=["x"], diagnosed_category="VERIFICATION_FAILURE", confidence=0.8)
    assert ev.failure_category == "VERIFICATION_FAILURE"
    assert "VERIFICATION" in ev.context_key()


# ---- no leakage ----
def test_policy_never_sees_fault_type():
    tasks = make_task_suite(n_per_fault=2, seed=3)
    env = ControlledEnv(tasks)
    g = base_genome()
    res = env.evaluate(g, tasks[0])
    ev = env.observe_failure(res, g)
    dumped = str(ev.to_dict())
    assert "FAULT_" not in dumped
    assert "fault_type" not in dumped


# ---- intervention credit ----
def test_credit_updates_and_averages():
    ic = InterventionCredit()
    ic.update(InterventionRecord("ctx:A", "M1", 0.2, 0.8, "t1"))
    ic.update(InterventionRecord("ctx:A", "M1", 0.2, 0.6, "t2"))
    m = ic.mean_credit("ctx:A", "M1")
    assert m > 0
    assert ic.n("ctx:A", "M1") == 2


# ---- policies run ----
def test_policies_select_valid_operator():
    ops = [M_INSERT_VERIFICATION, M_ADD_FAILURE_RECOVERY, M_CHANGE_TOOL_ROUTING, M_MODIFY_CONTEXT_FLOW]
    ev = FailureEvidence(task_id="t", genome_id="g")
    rng = random.Random(0)
    for pol in (RandomMutation(), GlobalAOS(), FailureConditionedPolicy(), ShuffledFailurePolicy()):
        op = pol.select(ev, ops, rng)
        assert op in ops


def test_fceol_uses_context():
    pol = FailureConditionedPolicy()
    ops = [M_INSERT_VERIFICATION, M_MODIFY_CONTEXT_FLOW]
    rng = random.Random(0)
    ev = evidence_from_trace(task_id="a", genome_id="g", symptoms=["wrong_output_passed"],
                             trace_ids=[], diagnosed_category="VERIFICATION_FAILURE", confidence=0.9)
    ctx = ev.context_key()
    # balanced sampling of both arms with mixed outcomes
    for _ in range(6):
        pol.update(InterventionRecord(ctx, M_INSERT_VERIFICATION, 0.2, 0.75, "a"))
        pol.update(InterventionRecord(ctx, M_MODIFY_CONTEXT_FLOW, 0.2, 0.22, "a"))
    # then strong positive for M1 only
    for _ in range(10):
        pol.update(InterventionRecord(ctx, M_INSERT_VERIFICATION, 0.1, 0.9, "a"))
    later = [pol.select(ev, ops, rng) for _ in range(40)]
    assert later.count(M_INSERT_VERIFICATION) > later.count(M_MODIFY_CONTEXT_FLOW)
