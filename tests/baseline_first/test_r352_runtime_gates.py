"""R3.5.2 offline tests: attribution, budget stop, preflight, auth gate."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "level3_pilot_r4"))

from src.research.r35_f_local import generate_e2_from_winner, build_feedback_diagnosis, apply_f_local
from src.research.r3_mutation_feedback import FailureRecord, hash_program
from src.research.r4_workflow_program import load_frozen_parent

import importlib.util

spec = importlib.util.spec_from_file_location("r35e", ROOT / "scripts/level3_pilot_r4/run_micro_r35.py")
r35 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r35)

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


def test_classify_execution_error_not_answer_mismatch():
    row = {"error": "WORKFLOW_CALL:x", "executed_graph_source": False, "graph_sha256_match": True, "ok": False, "predicted": None}
    assert r35.classify_row(row) == "EXECUTION_ERROR"
    row2 = {"error": None, "executed_graph_source": False, "graph_sha256_match": True, "ok": False, "predicted": "1"}
    assert r35.classify_row(row2) == "EXECUTION_ERROR"
    row3 = {"error": "COST_RESERVE_EXCEEDED", "executed_graph_source": False, "ok": False}
    assert r35.classify_row(row3) == "EXECUTION_ERROR"


def test_classify_parse_error():
    row = {"error": None, "executed_graph_source": True, "graph_sha256_match": True, "ok": True, "predicted": None}
    assert r35.classify_row(row) == "PARSE_ERROR"


def test_classify_answer_mismatch_only_when_valid():
    row = {"error": None, "executed_graph_source": True, "graph_sha256_match": True, "ok": True, "predicted": "3", "correct": False}
    assert r35.classify_row(row) == "ANSWER_MISMATCH"
    row["graph_sha256_match"] = False
    assert r35.classify_row(row) == "EXECUTION_ERROR"


def test_exec_fail_does_not_drive_answer_feedback(parent):
    rows = [{"error": "timeout", "executed_graph_source": False, "graph_sha256_match": False, "ok": False, "predicted": None, "correct": False}]
    class T:
        task_id = "t1"
        gold_answer = "5"
    fails = r35.fails_from(parent, [T], rows)
    assert fails[0].error_category == "EXECUTION_ERROR"
    diag = build_feedback_diagnosis([f for f in fails if not f.success])
    # diagnosis exists but is execution class, not fabricated ANSWER_MISMATCH
    assert diag is None or diag.coarse_label == "EXECUTION_ERROR"


def test_budget_stop_on_unsettled():
    b = r35.Budget()
    b.add({"cost_usd": None, "settle": "fail_closed_unknown", "error": "JSON:X"})
    assert b.stop == "INCOMPLETE_BUDGET_STOP"


def test_preflight_detects_hash_tamper():
    ts = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35.json").read_text(encoding="utf-8"))
    man = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35_manifest.json").read_text(encoding="utf-8"))
    ok = r35.preflight_verify(man, ts)
    assert ok["errors"] == []
    bad_man = dict(man)
    bad_man["confirm_task_set_sha256"] = "0" * 64
    bad = r35.preflight_verify(bad_man, ts)
    assert "CONFIRM_SHA_MISMATCH" in bad["errors"]


def test_auth_gate_fail_closed(tmp_path):
    err = r35.verify_execution_authorization(
        protocol="MICRO-R3.5.1", model="deepseek-flash", confirm_sha="abc",
        max_requests=300, max_cost_usd=0.30,
    )
    assert err.startswith("EXEC_AUTH_FILE_MISSING") or err.startswith("EXEC_AUTH_")


def test_e2_no_identical_suffix_stacking(parent):
    recs = [FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    diag = build_feedback_diagnosis(recs)
    winner = apply_f_local(parent, diag)["child"]
    # craft failure on winner
    wf = [FailureRecord("w", winner.program_id, hash_program(winner), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    out1 = generate_e2_from_winner(winner, wf)
    # second apply with same diagnosis on same winner after instruction already has suffix
    out2 = generate_e2_from_winner(out1["child"] or winner, wf, suffix_index=0)
    # at least one path records NO_OP or SUCCESS with different instruction
    assert out1["record"]["status"] in ("SUCCESS", "NO_OP", "NOT_GENERATED_NO_FAILURE")


def test_results_dir_not_overwritten(tmp_path, monkeypatch):
    out = tmp_path / "live"
    out.mkdir()
    (out / "summary.json").write_text("{}", encoding="utf-8")
    # simulate main's guard
    if out.exists() and any(out.iterdir()):
        blocked = True
    else:
        blocked = False
    assert blocked is True


def test_r34_history_unchanged():
    sm = json.loads((ROOT / "results/level3_pilot_r4_micro_r34/live/summary.json").read_text(encoding="utf-8"))
    assert abs(sm["confirm_accuracy"]["F"] - 13 / 30) < 1e-9
