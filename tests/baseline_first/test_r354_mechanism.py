"""R3.5.4 offline tests: A/O same text, prefix policy, taskset, no-feedback stop."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r354_mechanism import (
    BASE_STRATEGY_TEXT,
    PROTOCOL_ID,
    build_append_child,
    build_replace_child,
    diagnosis_from_dev_failures,
    freeze_baseline_b,
    feedback_text_for_label,
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


@pytest.fixture(scope="module")
def baseline():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    return freeze_baseline_b(parent)


def test_baseline_b_nonempty_frozen(baseline):
    B = baseline["program"]
    fr = baseline["freeze"]
    assert B.instruction == BASE_STRATEGY_TEXT
    assert fr["base_text"] == BASE_STRATEGY_TEXT
    assert len(fr["base_text_sha256"]) == 64
    assert fr["protocol_id"] == PROTOCOL_ID
    assert baseline.get("parent_program_id")
    assert fr["program_id"] == B.program_id


def test_a_and_o_same_feedback_text(baseline):
    B = baseline["program"]
    label = "ANSWER_MISMATCH"
    fb = feedback_text_for_label(label)
    a = build_append_child(B, label, feedback_id="fid1", source_task_ids=["t1"])
    o = build_replace_child(B, label, feedback_id="fid1", source_task_ids=["t1"])
    assert a["record"]["feedback_text_used"] == o["record"]["feedback_text_used"] == fb
    assert a["record"]["feedback_id"] == o["record"]["feedback_id"] == "fid1"
    assert a["record"]["source_task_ids"] == o["record"]["source_task_ids"] == ["t1"]


def test_a_preserves_base_prefix(baseline):
    B = baseline["program"]
    a = build_append_child(B, "ANSWER_MISMATCH", feedback_id="f", source_task_ids=["t"])
    assert a["child"] is not None
    assert a["record"]["base_prefix_preserved"] is True
    assert a["child"].instruction.startswith(BASE_STRATEGY_TEXT[:20])


def test_o_does_not_preserve_base_strategy(baseline):
    B = baseline["program"]
    o = build_replace_child(B, "ANSWER_MISMATCH", feedback_id="f", source_task_ids=["t"])
    assert o["child"] is not None
    assert o["record"]["base_prefix_preserved"] is False
    assert BASE_STRATEGY_TEXT[:20] not in (o["child"].instruction or "")
    assert o["child"].instruction.strip() == feedback_text_for_label("ANSWER_MISMATCH").strip()


def test_no_feedback_stops_mutation(baseline):
    B = baseline["program"]
    ok = [FailureRecord("t", B.program_id, hash_program(B), True, "NO_FAILURE")]
    assert diagnosis_from_dev_failures(ok) is None
    a = build_append_child(B, "NO_FAILURE", feedback_id="x", source_task_ids=[])
    assert a["child"] is None
    assert a["record"]["status"] in ("NO_USABLE_FEEDBACK", "NO_OP")


def test_tasksets_disjoint_and_hashed():
    man = json.loads((R354 / "taskset_r354_manifest.json").read_text(encoding="utf-8"))
    ts = json.loads((R354 / "taskset_r354.json").read_text(encoding="utf-8"))
    assert man["n_confirm"] == 30 and man["n_dev"] == 15
    cal = set(ts["calibration"]["indices"])
    dev = set(ts["dev"]["indices"])
    conf = set(ts["confirm"]["indices"])
    assert not cal & dev and not cal & conf and not dev & conf
    assert not (cal | dev | conf) & set(man["used_indices_excluded"])
    import hashlib

    def sha(block):
        blob = json.dumps(
            [(t["task_id"], " ".join(t["question"].split()), t["gold_answer"]) for t in block["tasks"]],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
    assert sha(ts["confirm"]) == man["confirm_task_set_sha256"]
    assert sha(ts["dev"]) == man["dev_task_set_sha256"]


def test_confirm_not_in_feedback(baseline):
    # feedback ids come only from dev failure records
    B = baseline["program"]
    fails = [FailureRecord("DEV_ONLY", B.program_id, hash_program(B), False, "ANSWER_MISMATCH", predicted="1", gold="2")]
    d = diagnosis_from_dev_failures(fails)
    assert d is not None
    assert d.source_task_ids == ["DEV_ONLY"]
    assert "CONFIRM" not in ",".join(d.source_task_ids)
