"""R3.3 guardrail tests. All tests are offline; no API or Docker call is made."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "level3_pilot_r4"))

import run_micro_r33 as m
from src.benchmark.gsm8k_tasks import GSM8KTask


def test_ledger_persists_reservation_before_send_and_charges_unknown_at_worst_case(tmp_path):
    ledger = m.R3Ledger(tmp_path / "ledger.json")
    reservation = ledger.reserve("short prompt", task_id="t1", phase="unit")
    assert reservation["ok"] is True
    assert ledger.n == 0
    assert (tmp_path / "ledger.json").exists()
    events = (tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(events[-1])["event"] == "PRE_SEND_RESERVED"

    ledger.mark_sending(reservation["request_id"])
    assert ledger.n == 1
    ledger.settle(
        reservation["request_id"],
        details={"error": "timeout"},
        billing_known=False,
        stop_reason="TEST_BILLING_UNKNOWN",
    )
    dumped = ledger.dump()
    assert dumped["stop_reason"] == "TEST_BILLING_UNKNOWN"
    assert dumped["budget_charged_upper_bound_usd"] == pytest.approx(reservation["reserved_cost_usd"])
    assert dumped["requests"][0]["billing_status"] == "UNKNOWN_RESERVED_AT_WORST_CASE"
    assert len((tmp_path / "ledger.jsonl").read_text(encoding="utf-8").splitlines()) == 3


def test_real_chat_missing_usage_fails_closed_without_zero_cost_settlement(monkeypatch, tmp_path):
    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps({
                "model": "deepseek-flash",
                "choices": [{"message": {"content": "Answer: 1"}}],
            }).encode("utf-8")

    class FakeOpener:
        def open(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only-not-a-real-key")
    monkeypatch.setattr(m.urllib.request, "build_opener", lambda *_args, **_kwargs: FakeOpener())
    ledger = m.R3Ledger(tmp_path / "ledger.json")
    result = m.real_chat("small prompt", ledger, task_id="t1", phase="unit")
    assert result["ok"] is False
    assert result["error"] == "USAGE_MISSING_OR_INVALID"
    assert ledger.stop == "USAGE_MISSING_OR_INVALID"
    assert ledger.n == 1
    assert ledger.dump()["budget_charged_upper_bound_usd"] > 0
    assert ledger.dump()["requests"][0]["actual_cost_usd"] is None


def test_mock_mode_requires_explicit_task_fixtures(tmp_path):
    task = GSM8KTask("task-1", "question", "1", "#### 1", "train")
    ledger = m.R3Ledger(tmp_path / "ledger.json")
    with pytest.raises(RuntimeError, match="MOCK_FIXTURE_NOT_CONFIGURED"):
        m.run_arm(object(), [task], ledger=ledger, phase="mock", mock_mode=True, extra_fixtures={})


def test_execution_failure_is_not_scored_as_model_answer(monkeypatch, tmp_path):
    task = GSM8KTask("task-1", "question", "1", "#### 1", "train")
    monkeypatch.setattr(m, "hash_program", lambda *_a, **_k: "fake-expected-sha")
    monkeypatch.setattr(m, "execute_candidate_docker", lambda *_a, **_k: {
        "ok": False,
        "error": "DOCKER_UNAVAILABLE",
        "answer_text": None,
        "executed_graph_source": False,
        "graph_sha256_match": False,
        "n_llm_calls": 0,
    })
    ledger = m.R3Ledger(tmp_path / "ledger.json")
    rows = m.run_arm(object(), [task], ledger=ledger, phase="real-test", mock_mode=False)
    assert rows[0]["execution_valid"] is False
    assert rows[0]["correct"] is None
    assert rows[0]["error"] == "DOCKER_UNAVAILABLE"


def test_paired_comparison_uses_same_task_ids_and_exact_mcnemar():
    base = [
        {"task_id": "a", "execution_valid": True, "correct": True},
        {"task_id": "b", "execution_valid": True, "correct": False},
        {"task_id": "c", "execution_valid": True, "correct": False},
    ]
    candidate = [
        {"task_id": "a", "execution_valid": True, "correct": False},
        {"task_id": "b", "execution_valid": True, "correct": True},
        {"task_id": "c", "execution_valid": True, "correct": False},
    ]
    result = m.paired_comparison(base, candidate)
    assert result["n"] == 3
    assert result["base_only_correct"] == 1
    assert result["candidate_only_correct"] == 1
    assert result["mcnemar_exact_p_two_sided"] == 1.0
    with pytest.raises(ValueError, match="PAIRED_TASK_SET_MISMATCH"):
        m.paired_comparison(base, candidate[:2])


def test_executor_hashes_the_exact_compiled_source():
    src = (ROOT / "src" / "research" / "r3_docker_executor.py").read_text(encoding="utf-8")
    assert 'compiled_sha = hashlib.sha256(graph_src.encode("utf-8")).hexdigest()' in src
    assert 'GRAPH_SHA_MISMATCH_BEFORE_EXECUTION' in src


def test_frozen_parent_placeholder_is_explicitly_labelled():
    from src.research.r4_workflow_program import load_frozen_parent

    parent = load_frozen_parent(ROOT / "results/level3_pilot_r2/frozen_candidates")
    assert parent.source_artifact_status == "KNOWN_PLACEHOLDER_UNREFERENCED"
    assert parent.lineage()["source_artifact_status"] == "KNOWN_PLACEHOLDER_UNREFERENCED"


def test_workflow_ipc_prevents_root_owned_bytecode_in_temp_mounts():
    source = (ROOT / "src/runtime/workflow_ipc.py").read_text(encoding="utf-8")
    assert 'run_user = ["--user", f"{os.getuid()}:{os.getgid()}"]' in source
    assert '"PYTHONDONTWRITEBYTECODE=1"' in source
    assert '"python", "-B", "runner.py"' in source
