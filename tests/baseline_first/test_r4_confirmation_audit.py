"""Regression + fault-injection tests for contamination audit (fail-closed)."""
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


def _clone_official_and_freeze(tmp_path: Path, *, tamper_freeze=False, tamper_official=False):
    root = tmp_path / "repo"
    (root / "results" / "level3_pilot_r31").mkdir(parents=True)
    (root / "docs" / "level3_pilot_r4_design" / "freeze").mkdir(parents=True)
    official_src = ROOT / "results/level3_pilot_r31/gsm8k_test_official.jsonl"
    data = official_src.read_bytes()
    if tamper_official:
        data = data + b"\n"
    (root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl").write_bytes(data)

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if tamper_freeze:
        freeze["task_set_sha256"] = "0" * 64
    fp = root / "docs" / "level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    fp.write_text(json.dumps(freeze), encoding="utf-8")
    return root, fp


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_official_and_freeze_gates_pass():
    report = mod.audit(ROOT, FREEZE)
    assert report["official_baseline"]["sha256_match"] is True
    assert report["official_baseline"]["record_count_match"] is True
    assert report["freeze_gate"]["ok"] is True
    assert report["gate_ok"] is True
    assert report["scan_errors"] == []
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"


def test_verdicts_not_auto_data_only():
    report = mod.audit(ROOT, FREEZE)
    for row in report["per_task"]:
        assert row["verdict"] in (mod.V_NO_HIT, mod.V_ALLOWED)
    assert report["summary"]["n_historical_scored"] == 0
    assert report["summary"]["n_inconclusive"] == 0


def test_r2_prior_scored_indices():
    report = mod.audit(ROOT, FREEZE)
    assert report["summary"]["r2_prior_scored_official_indices"] == [1, 2]
    assert report["summary"]["overlap_with_confirmation"] == []


def test_deterministic_twice():
    a = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    b = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    assert a == b


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

def test_official_sha_tamper_blocks(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path, tamper_official=True)
    report = mod.audit(root, fp)
    assert report["official_baseline"]["sha256_match"] is False
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_freeze_hash_tamper_blocks(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path, tamper_freeze=True)
    report = mod.audit(root, fp)
    assert report["freeze_gate"]["ok"] is False
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert report["per_task"][0]["verdict"] == mod.V_INCONCLUSIVE


def test_official_missing_blocks(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path)
    (root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl").unlink()
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert any("OFFICIAL_FILE_MISSING" in p for p in report["problems"])


def test_freeze_missing_blocks(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path)
    fp.unlink()
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert any("FREEZE_FILE_MISSING" in p for p in report["problems"])


def test_scan_root_missing_blocks_even_if_official_and_freeze_ok(tmp_path: Path):
    """CRITICAL: official + freeze pass, but scan error => BLOCKED (not VERIFIED)."""
    root, fp = _clone_official_and_freeze(tmp_path)
    # do NOT create src/ docs/ scripts/ tests/ — only results + freeze exist
    # SCAN_ROOTS includes src, docs, scripts, tests → missing
    report = mod.audit(root, fp)
    assert report["official_baseline"]["sha256_match"] is True
    assert report["freeze_gate"]["ok"] is True
    assert report["scan_errors"], "expected scan errors"
    assert any("SCAN_ROOT_MISSING" in e for e in report["scan_errors"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert report["independence"] != "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"
    assert report["gate_ok"] is False


def test_scan_error_blocks_verdicts(tmp_path: Path, monkeypatch):
    """Injected file-read error => final gate closed and verdicts INCONCLUSIVE."""
    root, fp = _clone_official_and_freeze(tmp_path)
    (root / "src").mkdir()
    bad = root / "src" / "x.py"
    bad.write_text("print(1)\n", encoding="utf-8")

    real_read = Path.read_bytes

    def flaky_read(self):
        if self.name == "x.py":
            raise OSError("SIMULATED_READ_FAIL")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", flaky_read)
    report = mod.audit(root, fp)
    assert any("FILE_READ_ERROR" in e for e in report["problems"] + report["scan_errors"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    for row in report["per_task"]:
        assert row["verdict"] == mod.V_INCONCLUSIVE


def test_r2_parse_error_blocks(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path)
    r2 = root / "results" / "level3_pilot_r2"
    r2.mkdir(parents=True, exist_ok=True)
    (r2 / "paired_confirmation_set.json").write_text("{not json", encoding="utf-8")
    report = mod.audit(root, fp)
    assert any("R2_PARSE_ERROR" in p for p in report["problems"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_known_scored_question_flagged(tmp_path: Path):
    root, fp = _clone_official_and_freeze(tmp_path)
    r2 = root / "results" / "level3_pilot_r2"
    r2.mkdir(parents=True, exist_ok=True)
    official = root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl"
    first_q = json.loads(official.read_text(encoding="utf-8").splitlines()[1])["question"]
    (r2 / "paired_experiment_results.json").write_text(
        json.dumps({"evidence_class": "SIMULATED", "tasks": [{"question": first_q}]}),
        encoding="utf-8",
    )
    # full v1 freeze still required for gate; inject scored hit on one task by
    # using a custom freeze that includes that question but FAILS the expected
    # hash — still must classify the hit and not claim VERIFIED.
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["tasks"][0]["question"] = first_q
    freeze["task_set_sha256"] = "0" * 64
    fp.write_text(json.dumps(freeze), encoding="utf-8")
    report = mod.audit(root, fp)
    hits = report["per_task"][0]["hits"]
    assert any(h["source_class"] == mod.C_SCORED for h in hits)
    assert report["independence"] in (
        "CONFIRMATION_INDEPENDENCE_BLOCKED",
        "CONFIRMATION_INDEPENDENCE_UNVERIFIED",
    )


def test_classify_verdict_matrix():
    assert mod.classify_verdict([], True) == mod.V_NO_HIT
    assert mod.classify_verdict([{"source_class": mod.C_OFFICIAL}], True) == mod.V_ALLOWED
    assert mod.classify_verdict([{"source_class": mod.C_SCORED}], True) == mod.V_SCORED
    assert mod.classify_verdict([{"source_class": mod.C_DECLARED}], True) == mod.V_DECLARED
    assert mod.classify_verdict([], False) == mod.V_INCONCLUSIVE
    assert mod.classify_verdict([{"source_class": mod.C_OTHER}], True) == mod.V_INCONCLUSIVE
