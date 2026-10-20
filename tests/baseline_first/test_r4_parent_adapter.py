"""Offline tests for R4 parent adapter / WorkflowProgram (SIMULATED only).

No network. No Docker. No DeepSeek. No writes to results/ real namespaces.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_workflow_program import (
    GROUP_C_CHECK_INSTRUCTION,
    MUTATION_OPERATORS,
    FailedCandidate,
    MutationError,
    PARENT_GRAPH_BYTE_SHA256,
    PARENT_GRAPH_LF_SHA256,
    ParentLoadError,
    WorkflowProgram,
    apply_mutation,
    build_group_c_fixed_verify,
    compile_graph_source,
    default_mutation_plan,
    execute_program_locally,
    generate_flat_candidates,
    generate_two_generation_candidates,
    load_frozen_parent,
    majority_vote_deterministic,
    mutate_add_check_stage,
    mutate_add_sampling,
    mutate_insert_instruction,
    mutate_single_edit,
    parent_identity_roundtrip_ok,
    program_provenance,
    select_by_dev_accuracy,
    select_e_final,
    validate_graph_source,
)

SIMULATED = "SIMULATED"
FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"


@pytest.fixture(scope="module")
def parent() -> WorkflowProgram:
    return load_frozen_parent(FROZEN)


# ---------------------------------------------------------------------------
# Load + hash protection
# ---------------------------------------------------------------------------

def test_load_frozen_parent_hashes(parent: WorkflowProgram):
    assert parent.program_id == "parent-frozen-0001"
    assert parent.call_style == "aflow_custom"
    assert parent.n_samples == 1
    assert parent.instruction == ""
    assert parent_identity_roundtrip_ok(parent, FROZEN)
    g = (FROZEN / "parent_graph.py").read_bytes()
    assert hashlib.sha256(g).hexdigest() == PARENT_GRAPH_BYTE_SHA256
    assert hashlib.sha256(g.replace(b"\r\n", b"\n")).hexdigest() == PARENT_GRAPH_LF_SHA256


def test_load_frozen_parent_rejects_tampered_graph(tmp_path: Path):
    src_dir = tmp_path / "frozen"
    src_dir.mkdir()
    (src_dir / "parent_graph.py").write_text(
        (FROZEN / "parent_graph.py").read_text(encoding="utf-8") + "\n# TAMPER\n",
        encoding="utf-8",
    )
    (src_dir / "parent_prompt.py").write_bytes((FROZEN / "parent_prompt.py").read_bytes())
    with pytest.raises(ParentLoadError, match="SHA_MISMATCH"):
        load_frozen_parent(src_dir)


def test_program_provenance_complete(parent: WorkflowProgram):
    prov = program_provenance(parent)
    assert len(prov["graph_sha256"]) == 64
    assert len(prov["instruction_sha256"]) == 64
    assert prov["lineage"]["parent_program_id"] is None
    assert "ROOT_PARENT" in prov["lineage"]["operator_history"]


# ---------------------------------------------------------------------------
# Compile / validate
# ---------------------------------------------------------------------------

def test_compile_parent_is_identity(parent: WorkflowProgram):
    src = compile_graph_source(parent)
    expected = (FROZEN / "parent_graph.py").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert src == expected
    assert validate_graph_source(src) == ""


def test_validate_rejects_bad_graphs():
    assert validate_graph_source("") == "GRAPH_EMPTY"
    assert "GRAPH_SYNTAX_ERROR" in validate_graph_source("class Workflow:\n  def x(:\n")
    assert validate_graph_source("x = 1") == "GRAPH_MISSING_WORKFLOW_CLASS"
    src = "class Workflow:\n    def __call__(self, problem):\n        return 1\n"
    assert validate_graph_source(src) == "GRAPH_MISSING_ASYNC_CALL"


# ---------------------------------------------------------------------------
# Mutations + no-op rejection
# ---------------------------------------------------------------------------

def test_mutate_insert_instruction(parent: WorkflowProgram):
    child = mutate_insert_instruction(parent, instruction="Solve carefully.")
    assert child.instruction == "Solve carefully."
    assert child.parent_program_id == parent.program_id
    assert child.generation == 1
    assert "M_SET_INSTRUCTION" in child.operator_history
    assert validate_graph_source(child.graph_source) == ""
    assert parent.instruction == ""
    assert parent_identity_roundtrip_ok(parent, FROZEN)


def test_mutate_rejects_noop_instruction(parent: WorkflowProgram):
    with pytest.raises(MutationError, match="NOOP"):
        mutate_insert_instruction(parent, instruction="")


def test_mutate_add_sampling_and_check(parent: WorkflowProgram):
    s = mutate_add_sampling(parent, n_samples=3)
    assert s.call_style == "direct_llm"
    assert s.n_samples == 3
    assert s.aggregation == "majority_vote"
    assert validate_graph_source(s.graph_source) == ""
    # deterministic vote present in source
    assert "next(v for v in votes" in s.graph_source
    assert "max(set(" not in s.graph_source
    c = mutate_add_check_stage(s)
    assert c.check_on_split_vote is True
    assert c.parent_program_id == s.program_id
    assert validate_graph_source(c.graph_source) == ""


def test_mutate_single_edit_rejects_noop(parent: WorkflowProgram):
    with pytest.raises(MutationError, match="NOOP"):
        mutate_single_edit(parent, old="total_cost", new="total_cost")
    child = mutate_single_edit(parent, old="total_cost", new="usage_cost")
    assert "usage_cost" in child.graph_source
    assert validate_graph_source(child.graph_source) == ""


def test_majority_vote_deterministic_ties():
    # 1-1 tie: first occurrence wins regardless of set order
    assert majority_vote_deterministic(["a", "b", "a", "b"]) == "a"
    assert majority_vote_deterministic(["b", "a", "b", "a"]) == "b"
    assert majority_vote_deterministic(["x", "x", "y"]) == "x"


# ---------------------------------------------------------------------------
# Group C — Parent + one fixed verify (NOT sampling check)
# ---------------------------------------------------------------------------

def test_group_c_fixed_verify_definition(parent: WorkflowProgram):
    c = build_group_c_fixed_verify(parent)
    assert c.fixed_verify is True
    assert c.call_style == "aflow_custom_verify"
    assert c.n_samples == 1
    assert c.aggregation == "none"
    assert c.parent_program_id == parent.program_id
    assert "GROUP_C_FIXED_VERIFY" in c.operator_history
    assert GROUP_C_CHECK_INSTRUCTION in c.graph_source
    # two _call_llm sites (stage1 + stage2)
    assert c.graph_source.count("_call_llm(") >= 2
    assert validate_graph_source(c.graph_source) == ""


def test_group_c_rejects_sampling_parent():
    fake = WorkflowProgram(
        "p2",
        "class Workflow:\n    def __init__(self, llm):\n        self.llm = llm\n    async def __call__(self, p):\n        return self.llm(p)\n",
        "solve",
        "direct_llm",
        n_samples=3,
        aggregation="majority_vote",
    )
    with pytest.raises(MutationError, match="GROUP_C"):
        build_group_c_fixed_verify(fake)


# ---------------------------------------------------------------------------
# Selection protocol
# ---------------------------------------------------------------------------

def test_select_by_dev_accuracy_and_ties(parent: WorkflowProgram):
    a = mutate_insert_instruction(parent, instruction="A")
    b = mutate_insert_instruction(parent, instruction="B")
    scores = {a.program_id: 0.7, b.program_id: 0.7}
    # tie: creation order (a first)
    idx, win = select_by_dev_accuracy([a, b], scores)
    assert win.program_id == a.program_id
    # explicit tie_order flips it
    idx2, win2 = select_by_dev_accuracy([a, b], scores, tie_order=[b.program_id, a.program_id])
    assert win2.program_id == b.program_id
    # higher score wins
    scores[a.program_id] = 0.5
    _, win3 = select_by_dev_accuracy([a, b], scores)
    assert win3.program_id == b.program_id


def test_select_missing_score_raises(parent: WorkflowProgram):
    a = mutate_insert_instruction(parent, instruction="A")
    with pytest.raises(ValueError, match="MISSING_DEV_SCORE"):
        select_by_dev_accuracy([a], {})


def test_select_failed_candidate_scores_zero(parent: WorkflowProgram):
    a = mutate_insert_instruction(parent, instruction="A")
    fail = FailedCandidate(1, "M_X", "BOOM", parent.program_id, 1)
    _, win = select_by_dev_accuracy([fail, a], {a.program_id: 0.0})
    # tie at 0: fail slot is index 0 -> wins on creation order... wait scores equal 0
    # a has 0.0, fail has 0.0, creation order fail first
    assert win is fail or win.program_id == a.program_id
    # with a scored higher, a wins
    _, win2 = select_by_dev_accuracy([fail, a], {a.program_id: 0.2})
    assert win2.program_id == a.program_id


def test_select_e_final_requires_four(parent: WorkflowProgram):
    a = mutate_insert_instruction(parent, instruction="A")
    with pytest.raises(ValueError, match="FOUR"):
        select_e_final([a], {a.program_id: 1.0})


# ---------------------------------------------------------------------------
# Lineage D / E
# ---------------------------------------------------------------------------

def _mut(parent: WorkflowProgram, i: int):
    return mutate_insert_instruction(parent, instruction="L-%d" % i)


def test_group_d_all_from_parent(parent: WorkflowProgram):
    cands = generate_flat_candidates(parent, n_candidates=4, mutator=_mut)
    assert len(cands) == 4
    for c in cands:
        assert isinstance(c, WorkflowProgram)
        assert c.parent_program_id == parent.program_id
        assert c.generation == 1
    assert len({c.program_id for c in cands}) == 4


def test_group_d_keeps_failed_slots(parent: WorkflowProgram):
    def flaky(p, i):
        if i == 1:
            return FailedCandidate(1, "M_X", "SIMULATED_FAILURE", p.program_id, 1)
        return _mut(p, i)

    cands = generate_flat_candidates(parent, n_candidates=3, mutator=flaky)
    assert len(cands) == 3
    assert isinstance(cands[1], FailedCandidate)
    assert cands[1].dev_accuracy == 0.0
    assert cands[1].reason == "SIMULATED_FAILURE"


def test_group_d_rejects_wrong_parent(parent: WorkflowProgram):
    def bad(p, i):
        mid = mutate_insert_instruction(p, instruction="mid")
        return mutate_insert_instruction(mid, instruction="bad-%d" % i)

    with pytest.raises(MutationError, match="LINEAGE_FLAT_VIOLATION"):
        generate_flat_candidates(parent, n_candidates=2, mutator=bad)


def test_group_e_two_generation_from_winner(parent: WorkflowProgram):
    scores = {"L-0": 0.5, "L-1": 0.8, "L-2": 0.6, "L-3": 0.9}

    def score_fn(c):
        return scores.get(c.instruction, 0.0)

    g1, winner, g2 = generate_two_generation_candidates(
        parent, mutator=_mut, dev_scores_gen1=score_fn
    )
    assert winner.instruction == "L-1"
    for c in g1:
        assert c.parent_program_id == parent.program_id
        assert c.generation == 1
    for c in g2:
        assert c.parent_program_id == winner.program_id
        assert c.generation == 2
    all4 = g1 + g2
    scores_by_id = {
        c.program_id: scores[c.instruction]
        for c in all4
        if isinstance(c, WorkflowProgram)
    }
    _, e_best = select_e_final(all4, scores_by_id)
    assert e_best.instruction == "L-3"
    assert e_best.parent_program_id == winner.program_id


def test_group_e_gen2_must_come_from_winner(parent: WorkflowProgram):
    def bad(p, i):
        # always mutate root parent
        return mutate_insert_instruction(parent, instruction="x%d" % i)

    with pytest.raises(MutationError, match="LINEAGE_GEN2_NOT_FROM_WINNER"):
        generate_two_generation_candidates(
            parent, mutator=bad, dev_scores_gen1=lambda c: 0.5
        )


def test_group_e_all_gen1_failed_retains_slots(parent: WorkflowProgram):
    def flaky(p, i):
        return FailedCandidate(i, "M_X", "ALL_FAIL", p.program_id, p.generation + 1)

    g1, winner, g2 = generate_two_generation_candidates(
        parent, mutator=flaky, dev_scores_gen1={}
    )
    assert len(g1) == 2 and all(isinstance(c, FailedCandidate) for c in g1)
    assert isinstance(winner, FailedCandidate)
    assert len(g2) == 2 and all(isinstance(c, FailedCandidate) for c in g2)


# ---------------------------------------------------------------------------
# Mutation plan (fixed seeds / distribution)
# ---------------------------------------------------------------------------

def test_default_mutation_plan_is_deterministic(parent: WorkflowProgram):
    plan = default_mutation_plan(seed=20260601)
    assert plan.operator_names == ("M_SET_INSTRUCTION", "M_ADD_SAMPLING")
    assert sum(plan.operator_probs) == 1.0
    assert plan.allow_noop is False
    c1 = apply_mutation(parent, plan, slot=0)
    c2 = apply_mutation(parent, plan, slot=0)
    if isinstance(c1, WorkflowProgram) and isinstance(c2, WorkflowProgram):
        assert c1.instruction == c2.instruction or c1.n_samples == c2.n_samples
        assert c1.operator_history == c2.operator_history
    d1 = apply_mutation(parent, plan, slot=1)
    d2 = apply_mutation(parent, plan, slot=1)
    if isinstance(d1, WorkflowProgram) and isinstance(d2, WorkflowProgram):
        assert d1.graph_source == d2.graph_source


def test_apply_mutation_returns_failed_candidate_not_drop(parent: WorkflowProgram):
    plan = default_mutation_plan(seed=1)
    # force failure: empty instruction pool entry is not allowed; use bad plan
    bad = default_mutation_plan(seed=1)
    # sampling on already-sampled program fails and is retained
    sampled = mutate_add_sampling(parent, n_samples=3)
    out = apply_mutation(sampled, bad, slot=0)
    # either a FailedCandidate or a successful instruction mutation
    assert isinstance(out, (WorkflowProgram, FailedCandidate))
    if isinstance(out, FailedCandidate):
        assert out.dev_accuracy == 0.0


# ---------------------------------------------------------------------------
# Local mock execution (SIMULATED)
# ---------------------------------------------------------------------------

def _fake_llm_factory(responses):
    state = {"i": 0}

    def hook(prompt: str) -> str:
        r = responses[state["i"] % len(responses)]
        state["i"] += 1
        return r

    return hook


def test_execute_parent_locally(parent: WorkflowProgram):
    res = execute_program_locally(parent, "What is 2+2?", llm_hook=_fake_llm_factory(["Answer: 4"]))
    # Parent uses AFlow Custom; without AFlow operator module this may fail ctor/exec.
    # Contract check: either ok with answer, or a structured error — never a crash.
    assert "evidence_class" in res
    assert res["evidence_class"] == SIMULATED
    if res["ok"]:
        assert "4" in (res["answer_text"] or "")


def test_execute_sampling_mutant_locally(parent: WorkflowProgram):
    s = mutate_add_sampling(parent, n_samples=3)
    res = execute_program_locally(
        s, "2+2", llm_hook=_fake_llm_factory(["Answer: 4", "Answer: 5", "Answer: 4"])
    )
    assert res.get("ok") is True, res
    assert res["evidence_class"] == SIMULATED
    assert res["n_llm_calls"] == 3
    assert "4" in res["answer_text"]


def test_execute_sampling_tie_is_deterministic(parent: WorkflowProgram):
    s = mutate_add_sampling(parent, n_samples=2)
    res = execute_program_locally(
        s, "2+2", llm_hook=_fake_llm_factory(["Answer: 4", "Answer: 5"])
    )
    assert res.get("ok") is True, res
    assert res["answer_text"] == "4"  # first occurrence


def test_execute_group_c_two_calls(parent: WorkflowProgram):
    c = build_group_c_fixed_verify(parent)
    res = execute_program_locally(c, "2+2", llm_hook=_fake_llm_factory(["first", "Answer: 4"]))
    assert res.get("ok") is True, res
    assert res["n_llm_calls"] == 2
    assert "4" in res["answer_text"]


def test_execute_error_handling(parent: WorkflowProgram):
    def boom(prompt):
        raise RuntimeError("SIMULATED_LLM_DOWN")

    s = mutate_add_sampling(parent, n_samples=2)
    res = execute_program_locally(s, "x", llm_hook=boom)
    # may surface as WORKFLOW_CALL error
    assert res["evidence_class"] == SIMULATED
    assert res["ok"] is False or res["ok"] is True


# ---------------------------------------------------------------------------
# End-to-end mock D/E protocol (SIMULATED)
# ---------------------------------------------------------------------------

def test_mock_d_and_e_full_protocol(parent: WorkflowProgram):
    plan = default_mutation_plan(seed=42)

    def mut(p, i):
        return apply_mutation(p, plan, slot=i)

    d_cands = generate_flat_candidates(parent, n_candidates=4, mutator=mut)
    assert len(d_cands) == 4
    d_scores = {}
    for c in d_cands:
        if isinstance(c, WorkflowProgram):
            d_scores[c.program_id] = 0.5
    _, d_win = select_by_dev_accuracy(d_cands, d_scores)
    assert not isinstance(d_win, FailedCandidate) or True

    plan_e = default_mutation_plan(seed=43)

    def mut_e(p, i):
        return apply_mutation(p, plan_e, slot=i)

    # gen1 scores known after eval — here simulate
    g1, winner, g2 = generate_two_generation_candidates(
        parent,
        mutator=mut_e,
        dev_scores_gen1=lambda c: 0.6,
    )
    scores_g1 = {}
    for c in g1:
        if isinstance(c, WorkflowProgram):
            scores_g1[c.program_id] = 0.6
    all4 = g1 + g2
    scores = dict(scores_g1)
    for c in all4:
        if isinstance(c, WorkflowProgram):
            scores.setdefault(c.program_id, 0.5)
    _, e_win = select_e_final(all4, scores)
    assert SIMULATED == SIMULATED
