"""R3.5 offline tests: F_LOCAL locality, feedback integrity, taskset freeze."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r35_f_local import apply_f_local, build_feedback_diagnosis
from src.research.r3_mutation_feedback import FailureRecord, hash_program
from src.research.r4_workflow_program import load_frozen_parent

R35 = ROOT / "results/level3_pilot_r4_micro_r35"
R34 = ROOT / "results/level3_pilot_r4_micro_r34"
SOCKETS = {"n": 0}


@pytest.fixture(autouse=True)
def _net(monkeypatch):
    real = socket.socket.connect

    def spy(self, *a, **k):
        host = a[0] if a else None
        if isinstance(host, tuple) and len(host) >= 1 and str(host[0]) not in ("127.0.0.1", "::1", "0.0.0.0", ""):
            SOCKETS["n"] += 1
            raise OSError("NETWORK_BLOCKED")
        return real(self, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", spy)
    yield
    assert SOCKETS["n"] == 0


@pytest.fixture(scope="module")
def parent():
    return load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")


def test_feedback_matches_real_failures(parent):
    fa = json.loads((R34 / "live/failure_archive.json").read_text(encoding="utf-8"))
    fails = [r for r in fa["calibration"] + fa["dev_parent"] if not r["success"]]
    assert fails
    recs = [
        FailureRecord(
            task_id=r["task_id"], parent_program_id=r["parent_program_id"],
            parent_graph_sha256=r["parent_graph_sha256"], success=False,
            error_category=r["error_category"], predicted=r.get("predicted"),
            gold=r.get("gold"), diagnosis_uses_gold=True,
        )
        for r in fails
    ]
    diag = build_feedback_diagnosis(recs)
    assert diag is not None
    assert set(diag.source_task_ids) <= {r["task_id"] for r in fails}
    assert diag.gold_in_candidate_prompt is False
    assert "HYPOTHESIS" in diag.possible_cause_hypothesis.upper() or "NOT" in diag.possible_cause_hypothesis.upper() or "unknown" in diag.possible_cause_hypothesis.lower()


def test_f_local_appends_not_replaces(parent):
    recs = [FailureRecord("t1", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    diag = build_feedback_diagnosis(recs)
    out = apply_f_local(parent, diag)
    child = out["child"]
    assert child is not None
    assert out["record"]["status"] == "SUCCESS"
    assert out["record"]["local_prefix_preserved"] is True
    # original instruction preserved as prefix (empty parent instruction -> "Solve the problem." base)
    assert child.instruction.startswith("Solve the problem.") or child.instruction.startswith(parent.instruction or "")
    assert hash_program(child) != hash_program(parent)


def test_no_feedback_rejected(parent):
    recs = [FailureRecord("t", parent.program_id, hash_program(parent), True, "NO_FAILURE")]
    assert build_feedback_diagnosis(recs) is None
    from src.research.r35_f_local import FeedbackDiagnosis
    d = FeedbackDiagnosis("x", "NO_FAILURE", "e", "h", "c", [], "s")
    out = apply_f_local(parent, d)
    assert out["child"] is None
    assert out["record"]["status"] == "NO_USABLE_FEEDBACK"


def test_e2_lineage_local(parent):
    recs = [FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    diag = build_feedback_diagnosis(recs)
    g1 = apply_f_local(parent, diag)["child"]
    e2 = apply_f_local(g1, diag)["child"]
    assert e2.parent_program_id == g1.program_id
    assert e2.generation == 2


def test_tasksets_disjoint_and_new():
    man = json.loads((R35 / "taskset_r35_manifest.json").read_text(encoding="utf-8"))
    ts = json.loads((R35 / "taskset_r35.json").read_text(encoding="utf-8"))
    assert man["n_dev"] == 20 and man["n_confirm"] == 30
    d = set(ts["dev"]["indices"])
    c = set(ts["confirm"]["indices"])
    assert not d & c
    used = set(man["used_indices_excluded"])
    assert not (d | c) & used


def test_r34_results_not_modified():
    sm = json.loads((R34 / "live/summary.json").read_text(encoding="utf-8"))
    assert abs(sm["confirm_accuracy"]["P"] - 22 / 30) < 1e-9
    assert abs(sm["confirm_accuracy"]["F"] - 13 / 30) < 1e-9


def test_gold_not_in_suffixes():
    from src.research.r35_f_local import F_LOCAL_SUFFIXES

    for pool in F_LOCAL_SUFFIXES.values():
        for s in pool:
            assert "Answer:" in s or "answer" in s.lower() or "Retry" in s or "Re-read" in s or "End with" in s
            # no long numeric gold-like dumps
            assert len([ch for ch in s if ch.isdigit()]) < 6
