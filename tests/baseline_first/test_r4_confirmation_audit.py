"""Regression tests for the reproducible confirmation contamination audit."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts/level3_pilot_r4/audit_confirmation_contamination.py"
spec = importlib.util.spec_from_file_location("conf_audit", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_official_baseline_reverified():
    report = mod.audit(ROOT, ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json")
    assert report["official_baseline"]["sha256_match"] is True
    assert report["official_baseline"]["record_count_match"] is True
    assert report["official_baseline"]["sha256"] == mod.OFFICIAL_SHA
    assert report["official_baseline"]["record_count"] == 1319


def test_r2_prior_scored_indices_detected():
    report = mod.audit(ROOT, ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json")
    # R2 really scored official test questions 1 and 2 — the audit must see them
    assert report["summary"]["r2_prior_scored_official_indices"] == [1, 2]
    # they must not be in the confirmation set
    assert report["summary"]["overlap_with_confirmation"] == []


def test_classification_rules():
    assert mod.classify_hit("results/level3_pilot_r2/paired_experiment_results.json", ["question_frag"]) == mod.CLASS_SCORED
    assert mod.classify_hit("results/level3_pilot_r31/gsm8k_test_official.jsonl", ["question_frag"]) == mod.CLASS_DATA_ONLY
    assert mod.classify_hit("docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json", ["question_frag"]) == mod.CLASS_DATA_ONLY
    assert mod.classify_hit("results/stage3_0_p1_r2a/gsm8k_split_manifest.json", ["index_field"]) == mod.CLASS_DECLARED


def test_audit_is_deterministic():
    freeze = ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json"
    a = json.dumps(mod.audit(ROOT, freeze), sort_keys=True)
    b = json.dumps(mod.audit(ROOT, freeze), sort_keys=True)
    assert a == b


def test_independence_and_counts():
    report = mod.audit(ROOT, ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json")
    assert report["summary"]["n_tasks"] == 40
    assert report["summary"]["n_scored_or_selected"] == 0
    assert report["summary"]["n_data_only"] == 40
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"
    assert report["scan_file_count"] > 0
    assert all("sha256" in row for row in report["scan_manifest"])


def test_known_scored_question_would_be_flagged(tmp_path: Path):
    """If a previously scored official question were in the freeze, it must flag.

    Uses R2 official index 1 (real historical scoring) against a temp scan
    root — SIMULATED contamination injection, not a claim about v1.
    """
    # Build a tiny synthetic tree
    root = tmp_path / "repo"
    (root / "results" / "level3_pilot_r31").mkdir(parents=True)
    (root / "results" / "level3_pilot_r2").mkdir(parents=True)
    (root / "docs" / "level3_pilot_r4_design" / "freeze").mkdir(parents=True)

    official = ROOT / "results/level3_pilot_r31/gsm8k_test_official.jsonl"
    (root / "results/level3_pilot_r31" / "gsm8k_test_official.jsonl").write_bytes(official.read_bytes())

    # take official index 1 question (historically scored by R2)
    first_q = json.loads(official.read_text(encoding="utf-8").splitlines()[1])["question"]
    scored_file = {
        "run_id": "SIMULATED",
        "evidence_class": "SIMULATED",
        "tasks": [{"task_id": "x", "question": first_q, "gold_answer": "3"}],
    }
    (root / "results" / "level3_pilot_r2" / "paired_experiment_results.json").write_text(
        json.dumps(scored_file), encoding="utf-8"
    )

    freeze = {
        "task_set_sha256": "SIMULATED",
        "tasks": [{
            "task_id": "gsm8k-official-test-0001",
            "question": first_q,
            "gold_answer": "3",
            "index": 1,
        }],
    }
    freeze_path = root / "docs/level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    freeze_path.write_text(json.dumps(freeze), encoding="utf-8")

    # monkeypatch SCAN to only include our tree via passing root
    report = mod.audit(root, freeze_path)
    assert report["per_task"][0]["verdict"] == "CONTAMINATED_SCORED"
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_UNVERIFIED"

