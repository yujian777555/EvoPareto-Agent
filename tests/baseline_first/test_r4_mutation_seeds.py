"""D/E mutation failure-path and seed-audit tests (offline, no API)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import (
    OPERATOR_SPECS,
    FailedCandidate,
    MutationError,
    WorkflowProgram,
    apply_mutation,
    default_mutation_plan,
    generate_flat_candidates,
    generate_two_generation_candidates,
    load_frozen_parent,
    mutate_add_sampling,
    mutate_insert_instruction,
    program_provenance,
)

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(FROZEN)


def test_operator_specs_complete():
    for name in ("M_SET_INSTRUCTION", "M_ADD_SAMPLING", "M_ADD_CHECK_STAGE", "M_SINGLE_EDIT"):
        assert name in OPERATOR_SPECS
        spec = OPERATOR_SPECS[name]
        for key in ("supported_style", "preconditions", "params", "semantics_after", "failure_reasons", "slot_effect"):
            assert key in spec


def test_noop_becomes_failed_candidate_not_abort(parent):
    plan = default_mutation_plan(seed=1)
    # force NOOP by emptying instruction pool to current value via custom plan
    from src.research.r4_workflow_program import MutationPlan

    noop_plan = MutationPlan(
        seed=1,
        operator_names=("M_SET_INSTRUCTION",),
        operator_probs=(1.0,),
        instruction_pool=("",),  # empty -> INSTRUCTION_EMPTY failure
        allow_noop=False,
    )
    out = apply_mutation(parent, noop_plan, slot=0)
    assert isinstance(out, FailedCandidate)
    assert out.reason in ("INSTRUCTION_EMPTY", "NOOP_MUTATION")
    assert out.dev_accuracy == 0.0


def test_sampling_on_sampled_candidate_is_failed_slot(parent):
    s = mutate_add_sampling(parent, n_samples=3)
    plan = default_mutation_plan(seed=2)
    # mutate sampled program: sampling op will fail, instruction may work
    from src.research.r4_workflow_program import MutationPlan

    only_sampling = MutationPlan(
        seed=3,
        operator_names=("M_ADD_SAMPLING",),
        operator_probs=(1.0,),
        instruction_pool=("x",),
    )
    out = apply_mutation(s, only_sampling, slot=0)
    assert isinstance(out, FailedCandidate)
    assert out.reason == "SAMPLING_REQUIRES_SINGLE_CALL_BASE"
    assert out.parent_program_id == s.program_id


def test_m_set_instruction_works_on_sampling_candidate(parent):
    s = mutate_add_sampling(parent, n_samples=3)
    child = mutate_insert_instruction(s, instruction="New solve text")
    assert child.instruction == "New solve text"
    assert "New solve text" in child.graph_source
    assert child.parent_program_id == s.program_id


def test_flat_generation_keeps_all_slots(parent):
    plan = default_mutation_plan(seed=20260601)

    def mut(p, i):
        return apply_mutation(p, plan, slot=i)

    cands = generate_flat_candidates(parent, n_candidates=4, mutator=mut)
    assert len(cands) == 4
    for c in cands:
        if isinstance(c, WorkflowProgram):
            assert c.parent_program_id == parent.program_id
        else:
            assert isinstance(c, FailedCandidate)


def test_e_gen2_lineage_and_ties(parent):
    plan = default_mutation_plan(seed=99)

    def mut(p, i):
        return apply_mutation(p, plan, slot=i)

    g1, winner, g2 = generate_two_generation_candidates(
        parent, mutator=mut, dev_scores_gen1=lambda c: 0.5
    )
    assert len(g1) == 2 and len(g2) == 2
    if isinstance(winner, WorkflowProgram):
        for c in g2:
            if isinstance(c, WorkflowProgram):
                assert c.parent_program_id == winner.program_id
                assert c.generation == winner.generation + 1


def test_seed_audit_script_runs(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "seed_audit", ROOT / "scripts/level3_pilot_r4/audit_mutation_seeds.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    report = mod.audit_seeds()
    assert report["base_seed"] == 20260601
    assert report["R_values"] == [6, 10]
    assert report["deterministic_rerun_slot0_block1"] is True
    assert report["summary"]["n_blocks"] == 16
    # every slot recorded
    assert len(report["rows"]) == 144
    # failures retained with reasons
    fails = [r for r in report["rows"] if r["status"] == "FAILED"]
    for f in fails:
        assert f["reason"]
        assert "slot" in f
    # D all success expected under default plan from frozen parent
    d_fail = [r for r in fails if r.get("kind") == "D"]
    assert d_fail == []



def test_m_single_edit_dispatch_requires_pool(parent):
    from src.research.r4_workflow_program import MutationPlan

    no_pool = MutationPlan(
        seed=1,
        operator_names=("M_SINGLE_EDIT",),
        operator_probs=(1.0,),
        instruction_pool=("x",),
        single_edit_pool=(),
    )
    out = apply_mutation(parent, no_pool, slot=0)
    assert isinstance(out, FailedCandidate)
    assert out.reason == "M_SINGLE_EDIT_NO_POOL"

    with_pool = MutationPlan(
        seed=1,
        operator_names=("M_SINGLE_EDIT",),
        operator_probs=(1.0,),
        instruction_pool=("x",),
        single_edit_pool=(("total_cost", "usage_cost"),),
    )
    child = apply_mutation(parent, with_pool, slot=0)
    assert isinstance(child, WorkflowProgram)
    assert "usage_cost" in child.graph_source
    assert child.parent_program_id == parent.program_id


def test_unknown_operator_is_failed_slot_not_silent(parent):
    from src.research.r4_workflow_program import MutationPlan

    bad = MutationPlan(
        seed=1,
        operator_names=("M_TOTALLY_FAKE",),
        operator_probs=(1.0,),
        instruction_pool=("x",),
    )
    out = apply_mutation(parent, bad, slot=3)
    assert isinstance(out, FailedCandidate)
    assert out.reason.startswith("UNKNOWN_OPERATOR")
    assert out.slot == 3
    assert out.dev_accuracy == 0.0


def test_operator_specs_enabled_flags():
    assert OPERATOR_SPECS["M_SET_INSTRUCTION"]["enabled_in_default_plan"] is True
    assert OPERATOR_SPECS["M_ADD_SAMPLING"]["enabled_in_default_plan"] is True
    assert OPERATOR_SPECS["M_SINGLE_EDIT"]["enabled_in_default_plan"] is False
    assert OPERATOR_SPECS["M_ADD_CHECK_STAGE"]["enabled_in_default_plan"] is False


def test_default_plan_distribution_unchanged():
    plan = default_mutation_plan(20260601)
    assert list(plan.operator_names) == ["M_SET_INSTRUCTION", "M_ADD_SAMPLING"]
    assert list(plan.operator_probs) == [0.5, 0.5]
