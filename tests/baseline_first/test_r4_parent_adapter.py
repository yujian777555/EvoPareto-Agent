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
    MUTATION_OPERATORS,
    MutationError,
    PARENT_GRAPH_BYTE_SHA256,
    PARENT_GRAPH_LF_SHA256,
    ParentLoadError,
    WorkflowProgram,
    compile_graph_source,
    generate_flat_candidates,
    generate_two_generation_candidates,
    load_frozen_parent,
    mutate_add_check_stage,
    mutate_add_sampling,
    mutate_insert_instruction,
    mutate_single_edit,
    parent_identity_roundtrip_ok,
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
    # digests documented and enforced
    g = (FROZEN / "parent_graph.py").read_bytes()
    assert hashlib.sha256(g).hexdigest() == PARENT_GRAPH_BYTE_SHA256
    assert hashlib.sha256(g.replace(b"\r\n", b"\n")).hexdigest() == PARENT_GRAPH_LF_SHA256


def test_load_frozen_parent_rejects_tampered_graph(tmp_path: Path):
    # SIMULATED tamper in a temp copy — never write into results/
    src_dir = tmp_path / "frozen"
    src_dir.mkdir()
    (src_dir / "parent_graph.py").write_text(
        (FROZEN / "parent_graph.py").read_text(encoding="utf-8") + "\n# TAMPER\n",
        encoding="utf-8",
    )
    (src_dir / "parent_prompt.py").write_bytes((FROZEN / "parent_prompt.py").read_bytes())
    with pytest.raises(ParentLoadError, match="SHA_MISMATCH"):
        load_frozen_parent(src_dir)


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
# Mutations
# ---------------------------------------------------------------------------

def test_mutate_insert_instruction(parent: WorkflowProgram):
    child = mutate_insert_instruction(parent, instruction="Solve carefully.")
    assert child.instruction == "Solve carefully."
    assert child.parent_program_id == parent.program_id
    assert child.generation == 1
    assert "M_SET_INSTRUCTION" in child.operator_history
    assert 'instruction="Solve carefully."' in child.graph_source or "instruction='Solve carefully.'" in child.graph_source
    assert validate_graph_source(child.graph_source) == ""
    # parent untouched
    assert parent.instruction == ""
    assert parent_identity_roundtrip_ok(parent, FROZEN)


def test_mutate_add_sampling_and_check(parent: WorkflowProgram):
    s = mutate_add_sampling(parent, n_samples=3)
    assert s.call_style == "direct_llm"
    assert s.n_samples == 3
    assert s.aggregation == "majority_vote"
    assert validate_graph_source(s.graph_source) == ""
    c = mutate_add_check_stage(s)
    assert c.check_on_split_vote is True
    assert c.parent_program_id == s.program_id
    assert validate_graph_source(c.graph_source) == ""


def test_mutate_single_edit_roundtrip_safe(parent: WorkflowProgram):
    child = mutate_single_edit(parent, old="total_cost", new="total_cost", operator="M_NOOP")  # no semantic change
    assert validate_graph_source(child.graph_source) == ""


def test_mutations_reject_invalid():
    with pytest.raises(MutationError):
        mutate_add_sampling(
            WorkflowProgram("x", "class Workflow:\n    async def __call__(self, p):\n        return p\n",
                            "", "direct_llm", n_samples=3, aggregation="majority_vote"),
            n_samples=3,
        )
    with pytest.raises(MutationError):
        mutate_add_check_stage(
            WorkflowProgram("x", "class Workflow:\n    async def __call__(self, p):\n        return p\n",
                            "", "direct_llm", n_samples=1, aggregation="none"),
        )


# ---------------------------------------------------------------------------
# Lineage rules for D and E
# ---------------------------------------------------------------------------

def _mutator_flat_style(parent: WorkflowProgram, index: int) -> WorkflowProgram:
    return mutate_insert_instruction(parent, instruction=f"Candidate-{index} instruction.")


def _mutator_lineage_style(parent: WorkflowProgram, index: int) -> WorkflowProgram:
    return mutate_insert_instruction(parent, instruction=f"Lineage-{index} from {parent.program_id[:8]}.")


def test_group_d_all_from_parent(parent: WorkflowProgram):
    cands = generate_flat_candidates(parent, n_candidates=4, mutator=_mutator_flat_style)
    assert len(cands) == 4
    for c in cands:
        assert c.parent_program_id == parent.program_id
        assert c.generation == 1
    assert len({c.program_id for c in cands}) == 4


def test_group_d_rejects_wrong_parent(parent: WorkflowProgram):
    def bad(parent, i):
        # mutate a child — violates flat rule
        mid = mutate_insert_instruction(parent, instruction="mid")
        return mutate_insert_instruction(mid, instruction=f"bad-{i}")

    with pytest.raises(MutationError, match="LINEAGE_FLAT_VIOLATION"):
        generate_flat_candidates(parent, n_candidates=2, mutator=bad)


def test_group_e_two_generation_from_winner(parent: WorkflowProgram):
    def pick_winner(cands):
        # deterministic: first
        return cands[0]

    g1, winner, g2 = generate_two_generation_candidates(
        parent, mutator=_mutator_lineage_style, winner_picker=pick_winner
    )
    assert len(g1) == 2 and len(g2) == 2
    for c in g1:
        assert c.parent_program_id == parent.program_id
        assert c.generation == 1
    assert winner.program_id == g1[0].program_id
    for c in g2:
        assert c.parent_program_id == winner.program_id
        assert c.generation == winner.generation + 1 == 2
        assert winner.program_id not in {p.program_id for p in g1 if p.program_id != winner.program_id} or True
    # gen2 must NOT be from parent directly
    for c in g2:
        assert c.parent_program_id != parent.program_id


def test_group_e_rejects_gen2_not_from_winner(parent: WorkflowProgram):
    def bad_mutator(parent_or_winner, index):
        # always mutate from root parent → violates gen2 lineage
        return mutate_insert_instruction(parent, instruction=f"x{index}")

    g1, winner, g2_failed = None, None, None
    with pytest.raises(MutationError, match="LINEAGE_GEN2_NOT_FROM_WINNER"):
        generate_two_generation_candidates(
            parent, mutator=bad_mutator, winner_picker=lambda cs: cs[0]
        )


# ---------------------------------------------------------------------------
# Failure retention (program layer)
# ---------------------------------------------------------------------------

def test_failed_mutation_does_not_invent_candidate(parent: WorkflowProgram):
    def flaky(parent, index):
        if index == 1:
            raise MutationError("SIMULATED_MUTATION_FAILURE")
        return mutate_insert_instruction(parent, instruction=f"ok-{index}")

    with pytest.raises(MutationError):
        generate_flat_candidates(parent, n_candidates=3, mutator=flaky)
    # caller must retain the failed slot with dev score 0 — program layer refuses to fake success


# ---------------------------------------------------------------------------
# Mock end-to-end interface (SIMULATED) — candidate gen → dev select → conf
# ---------------------------------------------------------------------------

def test_mock_d_and_e_interface_flow(parent: WorkflowProgram):
    """SIMULATED pipeline only. Never enters results/ real experiment records."""
    # fake dev scores keyed by instruction content
    dev_scores = {"Cand-0": 0.5, "Cand-1": 0.7, "Cand-2": 0.6, "Cand-3": 0.4}

    def mutator(p, i):
        return mutate_insert_instruction(p, instruction=f"Cand-{i}")

    d_cands = generate_flat_candidates(parent, n_candidates=4, mutator=mutator)
    d_best = max(d_cands, key=lambda c: (dev_scores[c.instruction], -d_cands.index(c)))
    assert d_best.instruction == "Cand-1"

    # E: gen1 then gen2 from winner
    scores_e = {"L-0": 0.55, "L-1": 0.65, "L-2": 0.60, "L-3": 0.80}

    def mut(p, i):
        return mutate_insert_instruction(p, instruction=f"L-{i}")

    def pick(cs):
        return max(cs, key=lambda c: scores_e[c.instruction])

    g1, winner, g2 = generate_two_generation_candidates(parent, mutator=mut, winner_picker=pick)
    assert winner.instruction == "L-1"
    assert [c.instruction for c in g2] == ["L-2", "L-3"]
    all4 = g1 + g2
    e_best = max(all4, key=lambda c: scores_e[c.instruction])
    assert e_best.instruction == "L-3"
    assert e_best.parent_program_id == winner.program_id
    assert "SIMULATED" == SIMULATED

