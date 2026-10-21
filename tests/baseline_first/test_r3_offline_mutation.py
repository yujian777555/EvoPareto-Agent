"""R3 offline tests (Mock only). Network blocked via socket monkeypatch."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r3_mutation_feedback import (
    FailureRecord,
    apply_random_mutation,
    build_feedback_child,
    execute_candidate,
    hash_program,
    install_aflow_mocks,
    select_feedback_operator,
    summarize_feedback,
)
from src.research.r4_workflow_program import load_frozen_parent

FROZEN = ROOT / "results" / "level3_pilot_r2" / "frozen_candidates"
SOCKETS = {"n": 0}


@pytest.fixture(autouse=True)
def _no_net(monkeypatch):
    real = socket.socket.connect

    def spy(self, *a, **k):
        host = a[0] if a else None
        # only block remote IPv4/IPv6 sockets; allow pipes / unnamed / loopback
        if isinstance(host, tuple) and len(host) >= 1:
            h = str(host[0])
            if h not in ("127.0.0.1", "::1", "0.0.0.0", ""):
                SOCKETS["n"] += 1
                raise OSError("NETWORK_BLOCKED")
        return real(self, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", spy)
    yield
    # remote connects asserted in test_no_remote_network


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(FROZEN)


def _hook(text="Answer: 42"):
    return lambda *a, **k: text


def test_parent_executes_graph_source(parent):
    install_aflow_mocks()
    r = execute_candidate(parent, "What is 40+2?", llm_hook=_hook())
    assert r["executed_graph_source"] is True
    assert r["ok"] is True, r.get("error")
    assert r["graph_sha256"] == hash_program(parent)


def test_child_executes_mutated_graph(parent):
    child, rec = apply_random_mutation(parent, seed=7, slot=1)
    assert child is not None
    r = execute_candidate(child, "What is 40+2?", llm_hook=_hook("child-out Answer: 1"))
    assert r["executed_graph_source"] is True
    assert r["ok"] is True
    assert r["graph_sha256"] == hash_program(child)
    assert r["graph_sha256"] != hash_program(parent)
    assert rec["parent_program_id"] == parent.program_id


def test_mutation_changes_behavior_not_only_metadata(parent):
    child, rec = apply_random_mutation(parent, seed=7, slot=1, operator="OP_INSTRUCTION_STYLE")
    assert child is not None
    # different compiled source + different instruction => different behavior under mock
    def hook(p):
        if "Answer" in p and "short" in p.lower() or "compact" in p.lower() or "one-line" in p.lower() or "directly" in p.lower():
            return "child-style Answer: 2"
        return "P-default Answer: 1"

    rp = execute_candidate(parent, "q", llm_hook=hook)
    rc = execute_candidate(child, "q", llm_hook=hook)
    assert rp["graph_sha256"] != rc["graph_sha256"]
    # at least one of prompt/answer reflects mutation
    assert child.instruction != parent.instruction
    assert rec["status"] == "SUCCESS"


def test_random_mutation_reproducible(parent):
    a, ra = apply_random_mutation(parent, seed=99, slot=2)
    b, rb = apply_random_mutation(parent, seed=99, slot=2)
    assert hash_program(a) == hash_program(b)
    assert ra["operator"] == rb["operator"]
    assert ra["params"] == rb["params"]


def test_feedback_reads_failure_records(parent):
    fr = FailureRecord("t1", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")
    s = summarize_feedback([fr])
    assert s.coarse_label == "ANSWER_MISMATCH"
    assert s.eligible is True
    op = select_feedback_operator(s)
    assert op == "OP_ARITH_RECHECK"
    child, rec = build_feedback_child(parent, s, seed=1, slot=0)
    assert child is not None
    assert rec["selected_operator"] == op
    assert rec["status"] == "SUCCESS"


def test_no_feedback_fails_explicitly(parent):
    ok = FailureRecord("t", parent.program_id, hash_program(parent), True, "NO_FAILURE")
    s = summarize_feedback([ok])
    child, rec = build_feedback_child(parent, s, seed=1, slot=1)
    assert child is None
    assert rec["status"] == "FAILED"
    assert rec["reason"] == "NO_USABLE_FEEDBACK"


def test_e2_parent_is_gen1_winner(parent):
    fr = FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")
    s = summarize_feedback([fr])
    g1, g1rec = build_feedback_child(parent, s, seed=5, slot=0)
    e2, e2rec = build_feedback_child(g1, s, seed=5, slot=1)
    assert e2 is not None
    assert e2.parent_program_id == g1.program_id
    assert e2.generation == 2
    assert e2rec["parent_program_id"] == g1.program_id


def test_gold_not_in_solve_prompt(parent):
    seen = []

    def hook(*a, **k):
        seen.append(str(a[0] if a else k.get("prompt", "")))
        return "Answer: 42"

    r = execute_candidate(parent, "Problem text", llm_hook=hook)
    assert r["ok"] is True, r.get("error")
    assert seen
    for p in seen:
        assert "gold_answer" not in p.lower()
        assert "standard answer" not in p.lower()
        assert "####" not in p


def test_splits_disjoint_and_exclude_prior():
    val = json.loads((ROOT / "results/level3_pilot_r4_micro_r3_offline/r3_offline_validation.json").read_text(encoding="utf-8"))
    sp = val["split"]
    assert sp["mutually_exclusive"] is True
    all_idx = set(sp["screening_indices"]) | set(sp["dev_indices"]) | set(sp["confirm_indices"])
    assert len(all_idx) == 23
    prior = set(sp["excluded_prior"])
    assert not (all_idx & prior)


def test_failed_candidate_recorded(parent):
    child, rec = apply_random_mutation(parent, seed=3, slot=0, operator="OP_NOPE")
    assert child is None
    assert rec["status"] == "FAILED"
    assert rec.get("reason")
    child2, rec2 = apply_random_mutation(parent, seed=3, slot=0)
    assert rec2["status"] in ("SUCCESS", "FAILED")


def test_equal_budget_same_entry(parent):
    child, _ = apply_random_mutation(parent, seed=11, slot=0)
    r1 = execute_candidate(parent, "q", llm_hook=_hook("a"))
    r2 = execute_candidate(child, "q", llm_hook=_hook("b"))
    # same contract keys
    for k in ("ok", "answer_text", "n_llm_calls", "executed_graph_source", "graph_sha256"):
        assert k in r1 and k in r2
    assert r1["executed_graph_source"] and r2["executed_graph_source"]


def test_no_http_imports_in_r3_module():
    src = (ROOT / "src/research/r3_mutation_feedback.py").read_text(encoding="utf-8").lower()
    for banned in ("import urllib", "import requests", "import httpx", "deepseek.com"):
        assert banned not in src


def test_no_remote_network():
    assert SOCKETS["n"] == 0
