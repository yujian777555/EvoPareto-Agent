"""Stage 3.0-P1 smoke tests (no real LLM)."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_aflow_source_pinned():
    af = ROOT / "external" / "AFlow"
    assert af.exists(), "AFlow clone required"
    import subprocess

    sha = subprocess.check_output(["git", "-C", str(af), "rev-parse", "HEAD"]).decode().strip()
    assert len(sha) == 40
    lic = (af / "LICENSE").read_text(encoding="utf-8")
    assert "MIT License" in lic


def test_external_gitignored():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "external/" in gi


def test_mock_smoke_results_present():
    p = ROOT / "results/stage3_0_p1/mock_smoke_results.json"
    assert p.exists()
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["static_import"] == "PASS"
    assert d["network_isolation"].startswith("PASS")
    assert d["live_real_model_evaluation"] == "NOT_EXECUTED"


def test_official_logs_empty_inventory():
    p = ROOT / "results/stage3_0_p1/historical_artifact_inventory.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d["results_json_all_empty"] is True
    assert d["official_traces_found"] is False


def test_paper_code_divergence_recorded():
    p = ROOT / "results/stage3_0_p1/source_code_map.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    assert "PAPER_CODE_DIVERGENCE" in d["paper_code_note"] or "PAPER_CODE_DIVERGENCE" in json.dumps(d)
