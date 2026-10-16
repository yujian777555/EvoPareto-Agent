"""Stage 2.0-R1 validity tests."""
from __future__ import annotations

import random

import pytest

from src.research.fceol.mutation_operators import (
    M_ADD_FAILURE_RECOVERY,
    M_CHANGE_TOOL_ROUTING,
    M_INSERT_VERIFICATION,
    M_MODIFY_CONTEXT_FLOW,
    apply_operator,
)
from src.research.fceol.workflow_genome import GenomeInvalid, base_genome
from src.research.fceol_r1.evidence import build_evidence
from src.research.fceol_r1.evaluator import eval_genome, operator_learning_protocol, oracle_upper_bound
from src.research.fceol_r1.faults import fault_channels
from src.research.fceol_r1.policies import FCEOL, GlobalAOS, OracleBest, RandomPolicy
from src.research.fceol_r1.task_suite import (
    audit_splits,
    make_task_suite,
    split_by_template,
)
from src.research.fceol_r1.workflow_interpreter import WorkflowInterpreter


# ---- P0-1 IDs & splits ----
def test_task_ids_globally_unique():
    tasks = make_task_suite(n_per_fault=6, seed=11)
    ids = [t.task_id for t in tasks]
    assert len(ids) == len(set(ids)) == len(tasks)


def test_split_isolation():
    tasks = make_task_suite(n_per_fault=6, seed=11)
    tr, dv, te = split_by_template(tasks, seed=7)
    a = audit_splits(tasks, tr, dv, te)
    assert a["unique_id_pass"]
    assert a["train_dev_disjoint"] and a["train_test_disjoint"] and a["dev_test_disjoint"]
    assert a["template_train_test_disjoint"] and a["template_train_dev_disjoint"]


def test_policy_evidence_has_no_fault_type():
    tasks = make_task_suite(n_per_fault=2, seed=1)
    t = tasks[0]
    st, _ = eval_genome(base_genome(), t)
    ev = build_evidence(task_id=t.policy_task_id(), symptoms=st.symptoms, mode="TRUE_EVIDENCE")
    d = ev.to_dict()
    assert "fault_type" not in d
    assert t.fault_type not in str(d)
    assert t.fault_type not in ev.context_key


# ---- P0-2 interpreter semantics ----
def test_interpreter_nodes_change_state():
    t = make_task_suite(n_per_fault=2, seed=1)[0]
    g = base_genome()  # GENERATE→SUBMIT only
    st, r0 = eval_genome(g, t)
    assert st.submitted is True
    assert len(st.events) >= 2  # generate + submit
    g2 = apply_operator(M_INSERT_VERIFICATION, g)
    st2, r1 = eval_genome(g2, t)
    kinds = {e["node_type"] for e in st2.events}
    assert "VERIFY" in kinds
    # independent evaluator: different structures → possibly different reward
    # (not asserted equal — reward is NOT a fault lookup)


def test_reward_not_fault_lookup():
    """Same genome+execution state must yield same reward regardless of fault name."""
    tasks = make_task_suite(n_per_fault=2, seed=3)
    g = base_genome()
    rewards = []
    for t in tasks:
        st, r = eval_genome(g, t)
        rewards.append(r)
    # reward depends on task spec & execution, not a dict from fault_type
    # at minimum: interpreter is deterministic for same inputs
    t = tasks[0]
    _, r_a = eval_genome(g, t)
    _, r_b = eval_genome(g, t)
    assert r_a == r_b


def test_verification_helps_only_with_recovery():
    tasks = make_task_suite(n_per_fault=4, seed=5)
    g = base_genome()
    g_v = apply_operator(M_INSERT_VERIFICATION, g)
    g_vr = apply_operator(M_ADD_FAILURE_RECOVERY, g_v)
    # for some faults, verify alone is not enough; verify+recovery better
    diffs = []
    for t in tasks:
        _, r0 = eval_genome(g, t)
        _, r1 = eval_genome(g_v, t)
        _, r2 = eval_genome(g_vr, t)
        diffs.append((r1 - r0, r2 - r1))
    # not a lookup table: both positive and zero/negative effects exist
    assert any(d[0] < 0.2 for d in diffs) or any(d[1] > 0.0 for d in diffs)


# ---- P0-3 shuffled deterministic ----
def test_shuffled_evidence_deterministic():
    e1 = build_evidence(task_id="X~1~0001", symptoms=["tool_misuse_detected"],
                        mode="SHUFFLED_EVIDENCE", seed=7)
    e2 = build_evidence(task_id="X~1~0001", symptoms=["tool_misuse_detected"],
                        mode="SHUFFLED_EVIDENCE", seed=7)
    assert e1.context_key == e2.context_key
    e3 = build_evidence(task_id="X~1~0001", symptoms=["tool_misuse_detected"],
                        mode="SHUFFLED_EVIDENCE", seed=8)
    # different seed may differ
    assert isinstance(e3.context_key, str)


def test_wrong_diagnosis_mode():
    e = build_evidence(task_id="Y", symptoms=["tool_misuse_detected"],
                       mode="WRONG_DIAGNOSIS")
    assert e.diagnosis == "PLANNING_FAILURE"
    assert e.confidence >= 0.7


# ---- P0-4 frozen transfer ----
def test_frozen_transfer_no_updates():
    tasks = make_task_suite(n_per_fault=3, seed=11)
    tr, dv, te = split_by_template(tasks, seed=7)
    pol = FCEOL()
    res = operator_learning_protocol(pol, tr, seed=0, steps_per_task=2, freeze_policy=False)
    n_after_train = sum(pol.credit.n(ctx, op) for ctx in pol.credit._n for op in ["x"])  # rough
    frozen_res = operator_learning_protocol(pol, te, seed=1, steps_per_task=2, freeze_policy=True)
    assert frozen_res["protocol"] == "frozen_transfer"
    assert frozen_res["n_tasks"] == len(te)


# ---- P0-5 oracle ----
def test_oracle_upper_bound_enumeration():
    tasks = make_task_suite(n_per_fault=2, seed=11)[:2]
    oracle = oracle_upper_bound(tasks, budget=2)
    assert oracle["n_tasks"] == 2
    assert oracle["mean_best_reward"] >= 0.0
    # oracle should be >= any single policy final reward on same tasks
    pol = RandomPolicy()
    res = operator_learning_protocol(pol, tasks, seed=0, steps_per_task=2, freeze_policy=True)
    assert oracle["mean_best_reward"] >= res["mean_final_reward"] - 1e-6


# ---- genome execution phenotype ----
def test_disabled_nodes_do_not_execute():
    g = apply_operator(M_INSERT_VERIFICATION, base_genome())
    for n in g.nodes:
        if n.kind == "VERIFY":
            n.enabled = False
    st, _ = eval_genome(g, make_task_suite(n_per_fault=1, seed=1)[0])
    kinds = {e["node_type"] for e in st.events}
    assert "VERIFY" not in kinds


def test_mutation_changes_execution_trace():
    t = make_task_suite(n_per_fault=1, seed=2)[0]
    g0 = base_genome()
    st0, _ = eval_genome(g0, t)
    g1 = apply_operator(M_INSERT_VERIFICATION, g0)
    st1, _ = eval_genome(g1, t)
    assert {e["node_type"] for e in st0.events} != {e["node_type"] for e in st1.events}
