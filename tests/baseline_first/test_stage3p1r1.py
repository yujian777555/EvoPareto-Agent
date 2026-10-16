"""Stage 3.0-P1-R1 smoke: evidence files + e2e trace present."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/stage3_0_p1_r1"


def test_e2e_mock_search_loop_passed():
    d = json.loads((OUT / "mock_execution_trace.json").read_text(encoding="utf-8"))
    assert d["official_search_loop"] == "PASS"
    assert d["experience_files"] >= 1
    assert d["results_json_written"] is True
    assert d["network_isolation"] == "MockLLM + MockEvaluator"


def test_mechanism_audit_quantified():
    d = json.loads((OUT / "search_mechanism_audit.json").read_text(encoding="utf-8"))
    freq = d["selection_audit"]["empirical_selection_freq_2000"]
    assert freq["2"] > 0.5  # best parent dominant
    dedup = d["experience_dedup_audit"]
    assert dedup["success_mod_blacklisted"] is True
    assert dedup["format_bans_successes_too"] is True


def test_history_insufficient_recorded():
    d = json.loads((OUT / "historical_artifact_inventory.json").read_text(encoding="utf-8"))
    assert d["official_traces_found"] is False
    assert d["results_json_all_empty_across_git_history"] is True
