"""R3.5.3 targeted tests: entry order, budget abort, unsettled cost, E2 NO_OP, index map."""
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

import importlib.util

spec = importlib.util.spec_from_file_location("r35e", ROOT / "scripts/level3_pilot_r4/run_micro_r35.py")
r35 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r35)

from src.research.r35_f_local import apply_f_local, build_feedback_diagnosis, generate_e2_from_winner
from src.research.r3_mutation_feedback import FailureRecord, hash_program
from src.research.r4_workflow_program import load_frozen_parent

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


def test_real_mode_requires_auth_not_unconditional_block():
    """Missing auth blocks; matching auth returns '' (entry proceeds)."""
    err = r35.verify_execution_authorization(
        protocol=r35.EXPERIMENT_PROTOCOL_ID,
        code_revision=r35.CODE_REVISION,
        model=r35.MODEL_ID,
        confirm_sha="x",
        max_requests=300,
        max_cost_usd=0.30,
    )
    assert err.startswith("EXEC_AUTH_FILE_MISSING") or err.startswith("EXEC_AUTH_")


def test_auth_fields_include_protocol_and_revision():
    assert r35.EXPERIMENT_PROTOCOL_ID == "MICRO-R3.5-EXP-v1"
    assert r35.CODE_REVISION == "r3.5.3"
    # mismatch on revision fails
    import tempfile, os

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "auth.json"
        path.write_text(json.dumps({
            "status": "AUTHORIZED", "protocol": r35.EXPERIMENT_PROTOCOL_ID,
            "model": r35.MODEL_ID, "confirm_task_set_sha256": "abc",
            "max_requests": 300, "max_cost_usd": 0.30,
            "code_revision": "r3.5.2",
        }), encoding="utf-8")
        os.environ[r35.AUTH_PATH_ENV] = str(path)
        try:
            err = r35.verify_execution_authorization(
                protocol=r35.EXPERIMENT_PROTOCOL_ID, code_revision=r35.CODE_REVISION,
                model=r35.MODEL_ID, confirm_sha="abc",
                max_requests=300, max_cost_usd=0.30,
            )
            assert err == "EXEC_AUTH_FIELD_MISMATCH:code_revision"
            # matching revision passes
            path.write_text(json.dumps({
                "status": "AUTHORIZED", "protocol": r35.EXPERIMENT_PROTOCOL_ID,
                "model": r35.MODEL_ID, "confirm_task_set_sha256": "abc",
                "max_requests": 300, "max_cost_usd": 0.30,
                "code_revision": r35.CODE_REVISION,
            }), encoding="utf-8")
            err2 = r35.verify_execution_authorization(
                protocol=r35.EXPERIMENT_PROTOCOL_ID, code_revision=r35.CODE_REVISION,
                model=r35.MODEL_ID, confirm_sha="abc",
                max_requests=300, max_cost_usd=0.30,
            )
            assert err2 == ""
        finally:
            os.environ.pop(r35.AUTH_PATH_ENV, None)


def test_budget_stop_skips_later_arms():
    b = r35.Budget()
    b.stop = "INCOMPLETE_BUDGET_STOP"

    class T:
        task_id = "x"

    rows = r35.run_arm(None, [T()], b, "conf:P", True)
    assert rows[0].get("skipped") is True
    assert rows[0]["counts_toward_accuracy"] is False
    assert rows[0]["skip_reason"] == "INCOMPLETE_BUDGET_STOP"


def test_unsettled_cost_not_reported_zero():
    b = r35.Budget()
    b.add({"cost_usd": 0.01, "settle": "settled_actual", "tokens_in": 1, "tokens_out": 1})
    b.add({"cost_usd": None, "settle": "fail_closed_unknown", "error": "JSON:X"})
    d = b.dump()
    assert d["unsettled_request_count"] >= 1
    assert d["cost_final"] is False
    assert d["total_cost_usd"] is None
    assert d["total_cost_note"] == "UNKNOWN_UNSETTLED"
    assert b.stop == "INCOMPLETE_BUDGET_STOP"


def test_classify_missing_sha_match_is_execution_error():
    row = {"error": None, "executed_graph_source": True, "ok": True, "predicted": "1", "correct": False}
    # graph_sha256_match missing
    assert r35.classify_row(row) == "EXECUTION_ERROR"
    row["graph_sha256_match"] = True
    assert r35.classify_row(row) == "ANSWER_MISMATCH"


def test_e2_second_identical_suffix_is_no_op(parent):
    recs = [FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    diag = build_feedback_diagnosis(recs)
    winner = apply_f_local(parent, diag)["child"]
    wf = [FailureRecord("w", winner.program_id, hash_program(winner), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    out1 = generate_e2_from_winner(winner, wf, suffix_index=1)
    assert out1["child"] is not None
    e2 = out1["child"]
    wf2 = [FailureRecord("w2", e2.program_id, hash_program(e2), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    # same suffix again -> NO_OP (suffix already present)
    out2 = generate_e2_from_winner(e2, wf2, suffix_index=1)
    assert out2["child"] is None
    assert out2["record"]["status"] in ("NO_OP", "NOT_GENERATED_NO_FAILURE")
    assert out2["record"].get("reason") in ("SUFFIX_ALREADY_PRESENT", "IDENTICAL_INSTRUCTION_TO_WINNER", "WINNER_NO_FAILURES")


def test_preflight_index_mapping():
    ts = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35.json").read_text(encoding="utf-8"))
    man = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35_manifest.json").read_text(encoding="utf-8"))
    ver = r35.preflight_verify(man, ts)
    assert ver["errors"] == []
    # tamper index mapping
    bad = json.loads(json.dumps(ts))
    bad["dev"]["indices"][0] = 99999
    ver2 = r35.preflight_verify(man, bad)
    assert any("TASK_ID_INDEX_MISMATCH" in e or "INDEX_NOT_IN_TRAIN" in e for e in ver2["errors"])


def test_classify_execution_fail_no_answer_feedback(parent):
    rows = [{"error": "timeout", "executed_graph_source": False, "graph_sha256_match": False, "ok": False, "predicted": None, "correct": False}]

    class T:
        task_id = "t1"
        gold_answer = "5"

    fails = r35.fails_from(parent, [T], rows)
    assert fails[0].error_category == "EXECUTION_ERROR"


def test_run_arm_stops_mid_arm_and_does_not_fabricate_failures(parent, monkeypatch):
    budget = r35.Budget()
    calls = []
    tasks = [
        r35.GSM8KTask("t0", "question 0", "1", "#### 1", "train"),
        r35.GSM8KTask("t1", "question 1", "2", "#### 2", "train"),
    ]

    def fake_execute(prog, question, *, llm, task_id, expect_graph_sha256):
        calls.append(task_id)
        budget.stop = "INCOMPLETE_BUDGET_STOP"
        return {
            "ok": False,
            "error": "UNKNOWN_USAGE",
            "answer_text": None,
            "executed_graph_source": False,
            "graph_sha256_match": False,
            "n_llm_calls": 1,
        }

    monkeypatch.setattr(r35, "execute_candidate_docker", fake_execute)
    rows = r35.run_arm(parent, tasks, budget, "dev:test", False)

    assert calls == ["t0"]
    assert len(rows) == 2
    assert rows[0]["counts_toward_accuracy"] is False
    assert rows[1]["skipped"] is True
    assert rows[1]["counts_toward_accuracy"] is False
    assert r35.accuracy(rows) is None
    assert r35.fails_from(parent, tasks, rows) == []
    assert r35.paired(rows, rows)["status"] == "INCOMPLETE"


def test_preflight_rejects_boolean_task_index():
    ts = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35.json").read_text(encoding="utf-8"))
    man = json.loads((ROOT / "results/level3_pilot_r4_micro_r35/taskset_r35_manifest.json").read_text(encoding="utf-8"))
    bad = json.loads(json.dumps(ts))
    bad["dev"]["indices"][0] = True
    result = r35.preflight_verify(man, bad)
    assert any("INDEX_TYPE_INVALID" in error for error in result["errors"])
