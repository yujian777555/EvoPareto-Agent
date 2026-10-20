"""Regression tests for the reproducible confirmation contamination audit (R3)."""
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

FREEZE = ROOT / "docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json"


def test_official_and_freeze_gates_pass():
    report = mod.audit(ROOT, FREEZE)
    assert report["official_baseline"]["sha256_match"] is True
    assert report["official_baseline"]["record_count_match"] is True
    assert report["freeze_gate"]["ok"] is True
    assert report["gate_ok"] is True
    assert report["scan_errors"] == []


def test_verdicts_are_not_auto_data_only():
    report = mod.audit(ROOT, FREEZE)
    # all 40 should be NO_HIT or ALLOWED_SOURCE_ONLY (not blanket DATA_ONLY)
    for row in report["per_task"]:
        assert row["verdict"] in (mod.V_NO_HIT, mod.V_ALLOWED)
    s = report["summary"]
    assert s["n_tasks"] == 40
    assert s["n_historical_scored"] == 0
    assert s["n_inconclusive"] == 0
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"


def test_r2_prior_scored_indices_detected():
    report = mod.audit(ROOT, FREEZE)
    assert report["summary"]["r2_prior_scored_official_indices"] == [1, 2]
    assert report["summary"]["overlap_with_confirmation"] == []


def test_source_classification_rules():
    assert mod.source_class("results/level3_pilot_r2/paired_experiment_results.json") == mod.C_SCORED
    assert mod.source_class("results/level3_pilot_r31/gsm8k_test_official.jsonl") == mod.C_OFFICIAL
    assert mod.source_class("docs/level3_pilot_r4_design/freeze/confirmation_set_v1_proposed.json") == mod.C_FREEZE
    assert mod.source_class("results/stage3_0_p1_r2a/gsm8k_split_manifest.json") == mod.C_DECLARED
    assert mod.source_class("src/research/r4_paired_stats.py") == mod.C_OTHER


def test_classify_verdict_matrix():
    ok = True
    assert mod.classify_verdict([], ok) == mod.V_NO_HIT
    assert mod.classify_verdict([{"source_class": mod.C_OFFICIAL}], ok) == mod.V_ALLOWED
    assert mod.classify_verdict([{"source_class": mod.C_FREEZE}], ok) == mod.V_ALLOWED
    assert mod.classify_verdict([{"source_class": mod.C_DECLARED}], ok) == mod.V_DECLARED
    assert mod.classify_verdict([{"source_class": mod.C_SCORED}], ok) == mod.V_SCORED
    assert mod.classify_verdict([{"source_class": mod.C_OFFICIAL}, {"source_class": mod.C_SCORED}], ok) == mod.V_SCORED
    assert mod.classify_verdict([], gate_ok=False) == mod.V_INCONCLUSIVE
    assert mod.classify_verdict([{"source_class": mod.C_OTHER}], ok) == mod.V_INCONCLUSIVE


def test_audit_is_deterministic():
    a = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    b = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    assert a == b


def test_hash_tamper_blocks_independence(tmp_path: Path):
    """If freeze hash gate fails, independence must be BLOCKED, not verified."""
    root = tmp_path / "repo"
    (root / "results" / "level3_pilot_r31").mkdir(parents=True)
    (root / "docs" / "level3_pilot_r4_design" / "freeze").mkdir(parents=True)
    official = ROOT / "results/level3_pilot_r31/gsm8k_test_official.jsonl"
    (root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl").write_bytes(official.read_bytes())

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["task_set_sha256"] = "0" * 64  # tamper declared hash
    fp = root / "docs/level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    fp.write_text(json.dumps(freeze), encoding="utf-8")

    report = mod.audit(root, fp)
    assert report["freeze_gate"]["ok"] is False
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert report["per_task"][0]["verdict"] == mod.V_INCONCLUSIVE


def test_missing_official_blocks(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "docs" / "level3_pilot_r4_design" / "freeze").mkdir(parents=True)
    fp = root / "docs/level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    fp.write_text(json.dumps({"task_set_sha256": mod.EXPECTED_V1_SHA, "tasks": []}), encoding="utf-8")
    report = mod.audit(root, fp)
    assert report["official_baseline"]["sha256_match"] is False
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_known_scored_question_flagged(tmp_path: Path):
    """SIMULATED injection: historically scored official question must flag SCORED."""
    root = tmp_path / "repo"
    (root / "results" / "level3_pilot_r31").mkdir(parents=True)
    (root / "results" / "level3_pilot_r2").mkdir(parents=True)
    (root / "docs" / "level3_pilot_r4_design" / "freeze").mkdir(parents=True)

    official = ROOT / "results/level3_pilot_r31/gsm8k_test_official.jsonl"
    (root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl").write_bytes(official.read_bytes())

    first_q = json.loads(official.read_text(encoding="utf-8").splitlines()[1])["question"]
    (root / "results" / "level3_pilot_r2" / "paired_experiment_results.json").write_text(
        json.dumps({"evidence_class": "SIMULATED", "tasks": [{"question": first_q}]}),
        encoding="utf-8",
    )
    freeze = {
        "task_set_sha256": mod.EXPECTED_V1_SHA,
        "tasks": [{
            "task_id": "gsm8k-official-test-0001",
            "question": first_q,
            "gold_answer": "3",
            "index": 1,
        }],
    }
    fp = root / "docs/level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    fp.write_text(json.dumps(freeze), encoding="utf-8")

    # freeze gate will fail (count/hash) -> BLOCKED; but hit must still be classified
    report = mod.audit(root, fp)
    assert report["per_task"][0]["n_hits"] >= 1
    assert any(h["source_class"] == mod.C_SCORED for h in report["per_task"][0]["hits"])
    assert report["independence"] in (
        "CONFIRMATION_INDEPENDENCE_BLOCKED",
        "CONFIRMATION_INDEPENDENCE_UNVERIFIED",
    )


def test_no_hit_vs_allowed_distinct(tmp_path: Path):
    """A task present only in the official file is ALLOWED; none is NO_HIT."""
    report = mod.audit(ROOT, FREEZE)
    allowed = [r for r in report["per_task"] if r["verdict"] == mod.V_ALLOWED]
    # freeze draft self-hit means many are ALLOWED, not NO_HIT
    assert len(allowed) + report["summary"]["n_no_hit"] == 40
    assert report["summary"]["n_no_hit"] + report["summary"]["n_allowed_source_only"] == 40
