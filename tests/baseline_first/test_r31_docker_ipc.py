"""R3.1 Docker/IPC integration tests (SIMULATED). Remote network count must be 0."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r3_docker_executor import (
    build_production_extras,
    evidence_executed_graph,
    execute_candidate_docker,
)
from src.research.r3_mutation_feedback import (
    FailureRecord,
    apply_random_mutation,
    build_feedback_child,
    hash_program,
    summarize_feedback,
)
from src.research.r4_workflow_program import load_frozen_parent

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
SOCKETS = {"n": 0}


@pytest.fixture(autouse=True)
def _block_remote(monkeypatch):
    real = socket.socket.connect

    def spy(self, *a, **k):
        host = a[0] if a else None
        if isinstance(host, tuple) and len(host) >= 1:
            h = str(host[0])
            if h not in ("127.0.0.1", "::1", "0.0.0.0", ""):
                SOCKETS["n"] += 1
                raise OSError("NETWORK_BLOCKED")
        return real(self, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", spy)
    yield
    assert SOCKETS["n"] == 0


class MockBox:
    def __init__(self, text="Reasoning. Answer: 42"):
        self.text = text
        self.calls = []

    def _request(self, prompt: str) -> str:
        self.calls.append(str(prompt))
        return self.text

    def get_usage_summary(self):
        return {"total_cost": 0.0}


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(FROZEN)


def test_parent_and_child_execute_different_graphs(parent):
    child, rec = apply_random_mutation(parent, seed=1, slot=0, operator="OP_INSTRUCTION_STYLE")
    rp = execute_candidate_docker(parent, "What is 2+2?", llm=MockBox("Answer: 4"), task_id="t1")
    rc = execute_candidate_docker(child, "What is 2+2?", llm=MockBox("Answer: 5"), task_id="t1")
    assert rp["graph_sha256"] != rc["graph_sha256"]
    assert rp["production_entry"] == "run_workflow_code_isolated"
    assert rc["production_entry"] == "run_workflow_code_isolated"


def test_graph_sha_matches_candidate(parent):
    child, _ = apply_random_mutation(parent, seed=2, slot=0)
    r = execute_candidate_docker(child, "q", llm=MockBox(), task_id="t2", expect_graph_sha256=hash_program(child))
    assert r["graph_sha256_match"] is True
    assert r["graph_sha256"] == hash_program(child)


def test_failed_container_not_reported_executed():
    bad = evidence_executed_graph({"ok": False, "error": "x", "answer_text": None})
    assert bad is False
    bad2 = evidence_executed_graph({"ok": True, "answer_text": "a", "docker_cleanup": {"container_created": False}})
    assert bad2 is False
    good = evidence_executed_graph({"ok": True, "answer_text": "a", "docker_cleanup": {"container_created": True, "error": None}})
    assert good is True


def test_parent_feedback_influences_operator(parent):
    fr = FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")
    s = summarize_feedback([fr])
    child, rec = build_feedback_child(parent, s, seed=9, slot=0)
    assert child is not None
    assert rec.get("selected_operator") or rec.get("operator") in (
        "OP_ARITH_RECHECK", "OP_REASONING_ORG", "M_SET_INSTRUCTION",
    )
    # E2 from winner
    e2, rec2 = build_feedback_child(child, s, seed=9, slot=1)
    assert e2.parent_program_id == child.program_id
    assert e2.generation == 2


def test_no_feedback_fails_explicitly(parent):
    ok = FailureRecord("t", parent.program_id, hash_program(parent), True, "NO_FAILURE")
    child, rec = build_feedback_child(parent, summarize_feedback([ok]), seed=1, slot=1)
    assert child is None
    assert rec["status"] == "FAILED"


def test_gold_not_in_docker_prompts(parent):
    box = MockBox("Answer: 42")
    r = execute_candidate_docker(parent, "Problem A", llm=box, task_id="t3")
    assert box.calls
    for p in box.calls:
        assert "gold" not in p.lower()
        assert "####" not in p


def test_reproducible_lineage(parent):
    a, ra = apply_random_mutation(parent, seed=5, slot=3)
    b, rb = apply_random_mutation(parent, seed=5, slot=3)
    assert hash_program(a) == hash_program(b)


def test_e2e_script_artifact_exists():
    p = ROOT / "results/level3_pilot_r4_micro_r31_offline/r31_e2e_validation.json"
    if not p.exists():
        pytest.skip("e2e artifact not generated")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["exec_flags"]["P"] is True
    assert data["graph_sha_match"]["P"] is True
    assert data["reproducible_mutations"] is True
    assert data["splits"]["disjoint"] is True
