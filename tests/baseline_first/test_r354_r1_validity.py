"""R3.5.4-R1 tests: validity/accuracy split, feedback purity, completion, preflight."""
from __future__ import annotations

import copy
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

spec = importlib.util.spec_from_file_location("r354e", ROOT / "scripts/level3_pilot_r4/run_micro_r354.py")
r354 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r354)

from src.research.r354_mechanism import (
    BASE_STRATEGY_TEXT,
    build_append_child,
    build_replace_child,
    diagnosis_from_dev_failures,
    freeze_baseline_b,
)
from src.research.r3_mutation_feedback import FailureRecord, hash_program
from src.research.r4_workflow_program import load_frozen_parent

R354 = ROOT / "results/level3_pilot_r4_micro_r354"
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


def _row(**kw):
    base = {
        "task_id": "t", "correct": False, "valid_eval": True,
        "executed_graph_source": True, "graph_sha256_match": True,
        "ok": True, "predicted": "1", "error": None, "skipped": False,
    }
    base.update(kw)
    return base


def test_docker_fail_not_in_accuracy():
    r = _row(correct=True, valid_eval=False, ok=False, error="NO_JSON_FOUND", executed_graph_source=False)
    assert r354.is_valid_eval(r) is False
    assert r354.classify_execution(r) == "EXECUTION_ERROR"
    assert r354.acc([r]) is None  # not 1.0


def test_sha_mismatch_not_in_paired():
    a = [_row(task_id="t1", correct=True)]
    b = [_row(task_id="t1", correct=False, graph_sha256_match=False, valid_eval=False)]
    p = r354.paired(a, b)
    assert p["status"] == "INCOMPLETE"
    assert "INVALID" in p["reason"]


def test_exec_fail_no_answer_feedback():
    rows = [_row(valid_eval=False, ok=False, error="timeout", executed_graph_source=False, graph_sha256_match=False, correct=None)]
    class T:
        task_id = "t1"
        gold_answer = "5"
    fails = r354.build_feedback_records(load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates"), [T()], rows)
    assert fails[0].error_category == "EXECUTION_ERROR"
    assert not fails[0].success


def test_parse_vs_answer_error():
    parse = _row(predicted=None, correct=False, valid_eval=False)
    ans = _row(predicted="3", correct=False, valid_eval=True)
    assert r354.classify_execution(parse) == "PARSE_ERROR"
    assert r354.classify_execution(ans) == "ANSWER_MISMATCH"


def test_missing_pair_never_complete():
    a = [_row(task_id="t1", correct=True)]
    b = [_row(task_id="t1", correct=True), _row(task_id="t2", correct=False)]
    assert r354.paired(a, b)["status"] == "INCOMPLETE"
    a2 = [_row(task_id="t1", valid_eval=False, skipped=True, correct=None)]
    assert r354.paired(a2, [_row(task_id="t1")])["status"] == "INCOMPLETE"


def test_invalid_eval_blocks_acc():
    assert r354.acc([_row(correct=True), _row(valid_eval=False, skipped=True, correct=None)]) is None
    assert r354.acc([_row(correct=True), _row(correct=False)]) == 0.5


def test_budget_caps():
    b = r354.Budget()
    assert r354.MAX_PHYSICAL == 150
    assert r354.MAX_COST_USD == 0.15
    b.n = 150
    assert b.precheck(10) == "INCOMPLETE_BUDGET_STOP"
    b2 = r354.Budget()
    b2.cost = 0.15
    assert b2.precheck(10) == "INCOMPLETE_BUDGET_STOP"


def test_unsettled_not_final_cost():
    b = r354.Budget()
    b.add({"cost_usd": 0.01, "settle": "settled_actual", "tokens_in": 1, "tokens_out": 1})
    b.add({"cost_usd": None, "settle": "fail_closed_unknown", "error": "X"})
    d = b.dump()
    assert d["cost_final"] is False
    assert d["total_cost_usd"] is None


def test_bao_feedback_constraints():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    pack = freeze_baseline_b(parent)
    B = pack["program"]
    a = build_append_child(B, "ANSWER_MISMATCH", feedback_id="FID", source_task_ids=["DEV1"])
    o = build_replace_child(B, "ANSWER_MISMATCH", feedback_id="FID", source_task_ids=["DEV1"])
    assert a["record"]["feedback_text_used"] == o["record"]["feedback_text_used"]
    assert a["record"]["feedback_id"] == o["record"]["feedback_id"] == "FID"
    assert a["record"]["base_prefix_preserved"] is True
    assert o["record"]["base_prefix_preserved"] is False


def test_confirm_not_in_feedback():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    B = freeze_baseline_b(parent)["program"]
    fails = [FailureRecord("DEVX", B.program_id, hash_program(B), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    d = diagnosis_from_dev_failures(fails)
    assert d.source_task_ids == ["DEVX"]


def test_preflight_tamper_zero_http():
    ts = json.loads((R354 / "taskset_r354.json").read_text(encoding="utf-8"))
    man = json.loads((R354 / "taskset_r354_manifest.json").read_text(encoding="utf-8"))
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    pack = freeze_baseline_b(parent)
    ok = r354.preflight_runtime(man, ts, pack["freeze"], {"feedback_text_used": "x"}, {"feedback_text_used": "x"})
    assert ok == []
    bad = json.loads(json.dumps(ts))
    bad["confirm"]["tasks"][0]["question"] = "TAMPERED"
    err = r354.preflight_runtime(man, bad, pack["freeze"], {"feedback_text_used": "x"}, {"feedback_text_used": "x"})
    assert any("SHA" in e or "COUNT" in e or "ID_INDEX" in e for e in err)
    assert SOCKETS["n"] == 0


def test_r353_history_unchanged():
    sm = json.loads((ROOT / "results/level3_pilot_r4_micro_r35_live_20261022_run2/summary.json").read_text(encoding="utf-8"))
    assert abs(sm["confirm_accuracy"]["P"] - 0.9) < 1e-9
    assert abs(sm["confirm_accuracy"]["F_old"] - 10 / 30) < 1e-6 or abs(sm["confirm_accuracy"]["F_old"] - 0.3333333333333333) < 1e-9
