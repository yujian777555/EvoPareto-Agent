"""R3.4 offline tests: taskset freeze, no overlap, budget gate, reproducibility."""
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r3_mutation_feedback import FailureRecord, build_feedback_child, hash_program, summarize_feedback
from src.research.r4_workflow_program import load_frozen_parent

TS = ROOT / "results/level3_pilot_r4_micro_r34"
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


def test_taskset_frozen_and_disjoint():
    ts = json.loads((TS / "taskset.json").read_text(encoding="utf-8"))
    man = json.loads((TS / "taskset_manifest.json").read_text(encoding="utf-8"))
    cal = {t["task_id"] for t in ts["calibration"]["tasks"]}
    dev = {t["task_id"] for t in ts["dev"]["tasks"]}
    conf = {t["task_id"] for t in ts["confirm"]["tasks"]}
    assert len(conf) >= 30
    assert not (cal & dev) and not (cal & conf) and not (dev & conf)
    used = set(man["used_indices_excluded"])
    idxs = set(ts["calibration"]["indices"]) | set(ts["dev"]["indices"]) | set(ts["confirm"]["indices"])
    assert not (idxs & used)
    assert man["confirm_used_for_selection"] is False


def test_taskset_hashes():
    import hashlib

    man = json.loads((TS / "taskset_manifest.json").read_text(encoding="utf-8"))
    ts = json.loads((TS / "taskset.json").read_text(encoding="utf-8"))

    def sha(block):
        items = block["tasks"]
        blob = json.dumps(
            [(t["task_id"], " ".join(t["question"].split()), t["gold_answer"]) for t in items],
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    assert sha(ts["confirm"]) == man["confirm_task_set_sha256"]
    assert sha(ts["calibration"]) == man["calibration_task_set_sha256"]


def test_train_sha():
    import hashlib

    assert hashlib.sha256((ROOT / "results/level3_pilot_r4_data/gsm8k_train_official.jsonl").read_bytes()).hexdigest() == \
        "17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465"


def test_no_feedback_f2_fails_closed():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    s = summarize_feedback([FailureRecord("t", parent.program_id, hash_program(parent), True, "NO_FAILURE")])
    child, rec = build_feedback_child(parent, s, seed=1, slot=0)
    assert child is None
    assert rec["status"] == "FAILED"


def test_real_failures_make_feedback():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    s = summarize_feedback([
        FailureRecord("t", parent.program_id, hash_program(parent), False, "ANSWER_MISMATCH", predicted="1", gold="2")
    ])
    child, rec = build_feedback_child(parent, s, seed=1, slot=0)
    assert child is not None
    assert rec.get("feedback_label") == "ANSWER_MISMATCH"


def test_e2_from_winner_lineage():
    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    from src.research.r3_mutation_feedback import apply_random_mutation

    w, _ = apply_random_mutation(parent, seed=2, slot=0, operator="OP_ARITH_RECHECK")
    s = summarize_feedback([FailureRecord("x", w.program_id, hash_program(w), False, "ANSWER_MISMATCH", predicted="1", gold="2")])
    e2, rec = build_feedback_child(w, s, seed=2, slot=1)
    assert e2.parent_program_id == w.program_id
    assert e2.generation == 2


def test_budget_precheck_blocks():
    sys.path.insert(0, str(ROOT / "scripts" / "level3_pilot_r4"))
    # import without running main
    import importlib.util

    spec = importlib.util.spec_from_file_location("r34", ROOT / "scripts/level3_pilot_r4/run_micro_r34.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    b = m.Budget()
    b.n = m.MAX_PHYSICAL
    assert b.precheck(100) == "REQUEST_CAP_REACHED"
    b2 = m.Budget()
    b2.cost = m.MAX_COST_USD
    assert b2.precheck(100) == "COST_RESERVE_EXCEEDED"
