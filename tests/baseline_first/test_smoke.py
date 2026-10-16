"""Baseline-first skeleton smoke tests (static + mock only)."""
from __future__ import annotations

import json

from src.research.baseline_first.adapter import (
    BaselineSpec,
    TraceRecord,
    audit_trace,
    environment_check,
    load_trace_json,
)


def test_static_import():
    spec = BaselineSpec(name="AFlow", paper_id="2410.10762",
                        code_url="https://github.com/FoundationAgents/AFlow")
    assert spec.repro_status == "NOT_EXECUTED"


def test_mock_trace_audit(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({
        "trace_id": "mock-1", "task_id": "T1", "source": "MOCK",
        "actions": ["a", "b", "a", "a"], "observations": ["o1", "o2", "o1", "o1"],
        "success": False,
    }), encoding="utf-8")
    tr = load_trace_json(p)
    rep = audit_trace(tr)
    assert rep["n_steps"] == 4
    assert rep["loop_occurrences"] == 2  # (o1,a) x3 → 2 extra occurrences
    assert rep["evidence_level"] == "SYNTHETIC"


def test_environment_check():
    env = environment_check()
    assert env["live_real_model_evaluation"] == "NOT_EXECUTED"
