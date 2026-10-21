"""Contamination audit tests: strict decode, fail-closed gates (R5)."""
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


def _clean_repo(tmp_path: Path, *, tamper_freeze=False, tamper_official=False, official_body=None):
    """Build a minimal clean scan tree that can achieve VERIFIED."""
    root = tmp_path / "repo"
    for d in ("results/level3_pilot_r31", "docs/level3_pilot_r4_design/freeze", "src", "scripts", "tests", "docs"):
        (root / d).mkdir(parents=True, exist_ok=True)
    official_src = ROOT / "results/level3_pilot_r31/gsm8k_test_official.jsonl"
    data = official_body if official_body is not None else official_src.read_bytes()
    if tamper_official and official_body is None:
        data = data + b"\n"
    (root / "results/level3_pilot_r31" / "gsm8k_test_official.jsonl").write_bytes(data)

    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    if tamper_freeze:
        freeze["task_set_sha256"] = "0" * 64
    fp = root / "docs/level3_pilot_r4_design" / "freeze" / "confirmation_set_v1_proposed.json"
    fp.write_text(json.dumps(freeze), encoding="utf-8")
    # harmless utf-8 text so scan roots exist
    (root / "src" / "ok.py").write_text("x = 1\n", encoding="utf-8")
    return root, fp


# ---------------------------------------------------------------------------
# Clean tree: VERIFIED possible
# ---------------------------------------------------------------------------

def test_clean_tree_can_verify(tmp_path):
    root, fp = _clean_repo(tmp_path)
    report = mod.audit(root, fp)
    assert report["official_baseline"]["sha256_match"] is True
    assert report["freeze_gate"]["ok"] is True
    assert report["gate_ok"] is True
    assert report["scan_errors"] == []
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"
    assert report["summary"]["n_no_hit"] == 40


def test_deterministic_repeat():
    a = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    b = json.dumps(mod.audit(ROOT, FREEZE), sort_keys=True)
    assert a == b


def test_no_hit_is_not_absolute_claim():
    report = mod.audit(ROOT, FREEZE)
    joined = " ".join(report.get("notes", []))
    assert "NO_HIT" in joined


# ---------------------------------------------------------------------------
# Fault injection
# ---------------------------------------------------------------------------

def test_invalid_utf8_blocks_independence(tmp_path):
    root, fp = _clean_repo(tmp_path)
    (root / "src" / "bad.py").write_bytes(b"print('ok')\n\xff\xfe\x00not-utf8\n")
    report = mod.audit(root, fp)
    assert any("FILE_DECODE_ERROR" in e for e in report["problems"] + report["scan_errors"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert report["gate_ok"] is False
    for row in report["per_task"]:
        assert row["verdict"] == mod.V_INCONCLUSIVE


def test_official_freeze_ok_but_scan_decode_fails(tmp_path):
    root, fp = _clean_repo(tmp_path)
    (root / "docs" / "notes.md").write_bytes(b"# hi\n\x80\x81\n")
    report = mod.audit(root, fp)
    assert report["official_baseline"]["sha256_match"] is True
    assert report["freeze_gate"]["ok"] is True
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
    assert report["independence"] != "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"


def test_official_sha_tamper_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path, tamper_official=True)
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_freeze_hash_tamper_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path, tamper_freeze=True)
    report = mod.audit(root, fp)
    assert report["freeze_gate"]["ok"] is False
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_official_missing_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path)
    (root / "results/level3_pilot_r31" / "gsm8k_test_official.jsonl").unlink()
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_freeze_missing_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path)
    fp.unlink()
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_scan_root_missing_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path)
    import shutil

    shutil.rmtree(root / "src")
    report = mod.audit(root, fp)
    assert any("SCAN_ROOT_MISSING" in e for e in report["scan_errors"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_file_read_error_blocks(tmp_path, monkeypatch):
    root, fp = _clean_repo(tmp_path)
    real_read = Path.read_bytes

    def flaky(self):
        if self.name == "ok.py":
            raise OSError("SIMULATED_READ_FAIL")
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", flaky)
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_r2_parse_error_blocks(tmp_path):
    root, fp = _clean_repo(tmp_path)
    r2 = root / "results" / "level3_pilot_r2"
    r2.mkdir(parents=True, exist_ok=True)
    (r2 / "paired_confirmation_set.json").write_text("{not json", encoding="utf-8")
    report = mod.audit(root, fp)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_known_scored_question_flagged(tmp_path):
    root, fp = _clean_repo(tmp_path)
    r2 = root / "results" / "level3_pilot_r2"
    r2.mkdir(parents=True, exist_ok=True)
    official = root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl"
    first_q = json.loads(official.read_text(encoding="utf-8").splitlines()[1])["question"]
    (r2 / "paired_experiment_results.json").write_text(
        json.dumps({"evidence_class": "SIMULATED", "tasks": [{"question": first_q}]}),
        encoding="utf-8",
    )
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["tasks"][0]["question"] = first_q
    freeze["task_set_sha256"] = "0" * 64
    fp.write_text(json.dumps(freeze), encoding="utf-8")
    report = mod.audit(root, fp)
    assert any(h["source_class"] == mod.C_SCORED for h in report["per_task"][0]["hits"])
    assert report["independence"] in (
        "CONFIRMATION_INDEPENDENCE_BLOCKED",
        "CONFIRMATION_INDEPENDENCE_UNVERIFIED",
    )


def test_binary_docker_stdout_excluded_not_decode_error(tmp_path):
    root, fp = _clean_repo(tmp_path)
    (root / "results" / "x").mkdir()
    (root / "results" / "x" / "docker_run_stdout.txt").write_bytes(b"\x00\x01\x02\xff")
    report = mod.audit(root, fp)
    assert report["gate_ok"] is True
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"


def test_real_repo_honestly_reports_legacy_decode_issue():
    """If the live repo has required-text decode failures, independence is BLOCKED.

    This test locks in fail-closed honesty: we do not claim VERIFIED while
    a scanned text file fails strict UTF-8 decode.
    """
    report = mod.audit(ROOT, FREEZE)
    decode_errors = [e for e in report["problems"] if "FILE_DECODE_ERROR" in e]
    if decode_errors:
        assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
        assert report["gate_ok"] is False
    else:
        assert report["independence"] in (
            "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH",
            "CONFIRMATION_INDEPENDENCE_UNVERIFIED",
        )


def test_classify_verdict_matrix():
    assert mod.classify_verdict([], True) == mod.V_NO_HIT
    assert mod.classify_verdict([{"source_class": mod.C_SCORED}], True) == mod.V_SCORED
    assert mod.classify_verdict([], False) == mod.V_INCONCLUSIVE
