"""R3.2 targeted tests: fixtures, E2 feedback source, mock rehearsal."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r3_mutation_feedback import (
    FailureRecord,
    build_feedback_child,
    hash_program,
    summarize_feedback,
)
from src.research.r4_workflow_program import load_frozen_parent

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


def test_task_fixture_mailbox_no_silent_default():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "e2e", ROOT / "scripts/level3_pilot_r4/r31_e2e_validation.py"
    )
    # don't exec main; just load class by reading source exec is heavy — import module without main
    sys.path.insert(0, str(ROOT / "scripts" / "level3_pilot_r4"))
    import r31_e2e_validation as m

    box = m.TaskFixtureMailbox("fixed-output Answer: 1")
    assert box._request("anything without task id") == "fixed-output Answer: 1"
    with pytest.raises(RuntimeError, match="FIXTURE_NOT_CONFIGURED"):
        m.UnconfiguredMailbox()._request("x")


def test_parent_dev_failure_creates_feedback(parent=None):
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    recs = [
        FailureRecord("t1", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2"),
        FailureRecord("t2", parent.program_id, hash_program(parent), True, "NO_FAILURE", predicted="2", gold="2"),
    ]
    s = summarize_feedback(recs)
    assert s.eligible is True
    assert s.coarse_label == "ANSWER_MISMATCH"


def test_e2_feedback_from_winner_not_parent():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    from src.research.r3_mutation_feedback import apply_random_mutation

    winner, _ = apply_random_mutation(parent, seed=1, slot=0, operator="OP_ARITH_RECHECK")
    # winner's own failure record
    s = summarize_feedback([
        FailureRecord("w1", winner.program_id, hash_program(winner), False, "ANSWER_MISMATCH", predicted="1", gold="2")
    ])
    e2, rec = build_feedback_child(winner, s, seed=2, slot=1)
    assert e2 is not None
    assert rec["parent_program_id"] == winner.program_id
    assert e2.parent_program_id == winner.program_id
    assert e2.generation == 2
    assert rec.get("feedback_label") == "ANSWER_MISMATCH"


def test_r32_e2e_artifact():
    p = ROOT / "results/level3_pilot_r4_micro_r32_offline/r32_e2e_validation.json"
    if not p.exists():
        pytest.skip("r32 e2e artifact missing")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["e2_parent_ok"] is True
    assert d["e2_generation"] == 2
    assert d["fixture_policy"]["silent_default_fallback"] is False
    assert d["confirm_used_for_selection"] is False
    assert d["exec_flags"]["P"] is True


def test_mock_rehearsal_zero_api():
    p = ROOT / "results/level3_pilot_r4_micro_r3_run/summary.json"
    if not p.exists():
        pytest.skip("rehearsal summary missing")
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["mock_mode"] is True
    assert d["requests_total"] == 0
    assert d["cost_usd_total"] == 0.0
    assert d["e2_parent_ok"] is True


def test_docker_exec_sha_consistent():
    from src.research.r3_docker_executor import execute_candidate_docker

    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    sha = hash_program(parent)
    box = type("B", (), {"_request": lambda self, p: "Answer: 1", "get_usage_summary": lambda self: {"total_cost": 0.0}})()
    r = execute_candidate_docker(parent, "q", llm=box, task_id="x", expect_graph_sha256=sha)
    assert r["graph_sha256"] == sha
    assert r["graph_sha256_match"] is True
