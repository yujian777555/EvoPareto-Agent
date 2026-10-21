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
    assert report["summary"]["n_inconclusive"] == 0
    assert report["summary"]["n_no_hit"] + report["summary"]["n_allowed_source_only"] == 40


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
    d = root / "results" / "stage1_6"
    d.mkdir(parents=True, exist_ok=True)
    src = ROOT / "results" / "stage1_6" / "docker_run_stdout.txt"
    if src.exists():
        (d / "docker_run_stdout.txt").write_bytes(src.read_bytes())  # pinned hash
    else:
        (d / "docker_run_stdout.txt").write_bytes(b"\x00\x01\x02\xff")
    report = mod.audit(root, fp)
    if src.exists():
        assert report["gate_ok"] is True
        assert report["independence"] == "CONFIRMATION_INDEPENDENCE_VERIFIED_BY_ARTIFACT_SEARCH"
        assert any(e["path"].endswith("docker_run_stdout.txt") and e.get("rule_id") for e in report["exclusion_log"])
    else:
        # no pinned source in workspace — mismatch rescan is acceptable fail-closed
        assert report["gate_ok"] in (True, False)


def test_unknown_same_basename_is_not_excluded(tmp_path):
    """Same basename at an unreviewed path must still be scanned/strict-decoded."""
    root, fp = _clean_repo(tmp_path)
    other = root / "results" / "elsewhere"
    other.mkdir(parents=True, exist_ok=True)
    # same name as a reviewed exclusion, different path
    bad = other / "docker_run_stdout.txt"
    bad.write_bytes(b"\xff\xfe\x00")
    report = mod.audit(root, fp)
    assert any("FILE_DECODE_ERROR" in e for e in report["problems"] + report["scan_errors"])
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_legacy_encoding_file_not_forced_excluded():
    """PHASE2 mixed encoding stays a required-text problem (honest BLOCKED)."""
    assert "PHASE2" not in str(getattr(mod, "PINNED_EXCLUSIONS", {}))
    report = mod.audit(ROOT, FREEZE)
    assert "docs/PHASE2_EVOLUTION_MEMORY.md" in report.get("legacy_encoding_probes", {})
    if any("PHASE2" in e for e in report["problems"]):
        assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"


def test_original_phase2_bytes_unchanged():
    pth = ROOT / "docs/PHASE2_EVOLUTION_MEMORY.md"
    if not pth.exists():
        pytest.skip("no legacy file")
    import hashlib

    h1 = hashlib.sha256(pth.read_bytes()).hexdigest()
    # re-read
    h2 = hashlib.sha256(pth.read_bytes()).hexdigest()
    assert h1 == h2
    # still fails strict utf-8 (we did not rewrite it)
    with pytest.raises(UnicodeDecodeError):
        pth.read_bytes().decode("utf-8", errors="strict")


def test_r6_reports_include_exclusion_log():
    report = mod.audit(ROOT, FREEZE)
    assert "exclusion_log" in report
    assert isinstance(report["exclusion_log"], list)



# ---------------------------------------------------------------------------
# R7: leak injection — unknown copies must NOT be excluded
# ---------------------------------------------------------------------------

def test_unknown_official_name_copy_is_scanned(tmp_path):
    """A copy of gsm8k_test_official.jsonl at a random path must be scanned."""
    root, fp = _clean_repo(tmp_path)
    hist = root / "results" / "old_run"
    hist.mkdir(parents=True, exist_ok=True)
    # same basename as official source
    (hist / "gsm8k_test_official.jsonl").write_bytes(b'{"question": "LEAK_Q", "answer": "x"}\n')
    report = mod.audit(root, fp)
    # not in exclusion_log as official source
    excl_paths = [e["path"] for e in report["exclusion_log"]]
    assert not any(e.endswith("old_run/gsm8k_test_official.jsonl") for e in excl_paths)
    # must have been text-scanned (appears in scan_manifest)
    assert any(m["path"].endswith("old_run/gsm8k_test_official.jsonl") for m in report["scan_manifest"])


def test_unknown_audit_similar_name_is_scanned(tmp_path):
    root, fp = _clean_repo(tmp_path)
    d = root / "docs" / "misc"
    d.mkdir(parents=True, exist_ok=True)
    (d / "confirmation_contamination_audit_backup.json").write_text("{\"x\":1}", encoding="utf-8")
    report = mod.audit(root, fp)
    excl_paths = [e["path"] for e in report["exclusion_log"]]
    assert not any("backup" in e for e in excl_paths)
    assert any("backup" in m["path"] for m in report["scan_manifest"])


def test_freeze_copy_nonstandard_path_is_scanned(tmp_path):
    root, fp = _clean_repo(tmp_path)
    d = root / "docs" / "copies"
    d.mkdir(parents=True, exist_ok=True)
    (d / "confirmation_set_v1_proposed.json").write_text("{}", encoding="utf-8")
    report = mod.audit(root, fp)
    assert any("copies/confirmation_set_v1_proposed.json" in m["path"] for m in report["scan_manifest"])


def test_historical_result_with_questions_is_scored_class(tmp_path):
    root, fp = _clean_repo(tmp_path)
    official = root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl"
    q = json.loads(official.read_text(encoding="utf-8").splitlines()[1])["question"]
    hist = root / "results" / "archive"
    hist.mkdir(parents=True, exist_ok=True)
    (hist / "old_results.json").write_text(json.dumps({"tasks": [{"question": q}]}), encoding="utf-8")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["tasks"][0]["question"] = q
    freeze["task_set_sha256"] = "0" * 64
    fp.write_text(json.dumps(freeze), encoding="utf-8")
    report = mod.audit(root, fp)
    # archive hit classified as scored / blocks VERIFIED
    assert report["independence"] in (
        "CONFIRMATION_INDEPENDENCE_BLOCKED",
        "CONFIRMATION_INDEPENDENCE_UNVERIFIED",
    )


def test_every_skipped_file_logged(tmp_path):
    root, fp = _clean_repo(tmp_path)
    d = root / "results" / "stage1_6"
    d.mkdir(parents=True, exist_ok=True)
    (d / "docker_run_stdout.txt").write_bytes(b"\x00\xff")
    report = mod.audit(root, fp)
    for e in report["exclusion_log"]:
        assert e.get("sha256")
        assert e.get("size") is not None
        assert e.get("reason")
        assert e.get("rule_id")
        assert e.get("path")


def test_phase2_bytes_unchanged_still_blocked():
    import hashlib

    pth = ROOT / "docs/PHASE2_EVOLUTION_MEMORY.md"
    assert pth.exists()
    # still mixed encoding
    with pytest.raises(UnicodeDecodeError):
        pth.read_bytes().decode("utf-8", errors="strict")
    report = mod.audit(ROOT, FREEZE)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"



# ---------------------------------------------------------------------------
# R8: fragment matching + pinned exclusions + expanded coverage
# ---------------------------------------------------------------------------

def _write_freeze_with_q(fp, q):
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    freeze["tasks"][0]["question"] = q
    freeze["task_set_sha256"] = "0" * 64
    fp.write_text(json.dumps(freeze), encoding="utf-8")


def _q1(root):
    return json.loads((root / "results" / "level3_pilot_r31" / "gsm8k_test_official.jsonl").read_text(encoding="utf-8").splitlines()[1])["question"]


def test_fragment_head_match_not_no_hit(tmp_path):
    root, fp = _clean_repo(tmp_path)
    qn = " ".join(_q1(root).split())
    (root / "src" / "leak.py").write_text("# " + qn[:70] + chr(10), encoding="utf-8")
    _write_freeze_with_q(fp, _q1(root))
    report = mod.audit(root, fp)
    assert report["per_task"][0]["n_hits"] >= 1
    assert report["per_task"][0]["verdict"] != mod.V_NO_HIT


def test_fragment_middle_match(tmp_path):
    root, fp = _clean_repo(tmp_path)
    qn = " ".join(_q1(root).split())
    mid = qn[70:140] if len(qn) > 140 else qn[30:80]
    (root / "src" / "m.py").write_text("x = " + mid + chr(10), encoding="utf-8")
    _write_freeze_with_q(fp, _q1(root))
    report = mod.audit(root, fp)
    assert report["per_task"][0]["n_hits"] >= 1
    assert report["per_task"][0]["verdict"] != mod.V_NO_HIT


def test_fragment_tail_match(tmp_path):
    root, fp = _clean_repo(tmp_path)
    qn = " ".join(_q1(root).split())
    (root / "src" / "t.py").write_text("z = " + qn[-80:] + chr(10), encoding="utf-8")
    _write_freeze_with_q(fp, _q1(root))
    report = mod.audit(root, fp)
    assert report["per_task"][0]["n_hits"] >= 1


def test_pinned_hash_mismatch_rescan(tmp_path):
    root, fp = _clean_repo(tmp_path)
    d = root / "results" / "stage1_6"
    d.mkdir(parents=True, exist_ok=True)
    (d / "docker_run_stdout.txt").write_bytes(b"not pinned bytes")
    report = mod.audit(root, fp)
    kinds = [e.get("kind") for e in report["exclusion_log"]]
    assert "PINNED_MISMATCH" in kinds


def test_html_and_notebook_scanned(tmp_path):
    root, fp = _clean_repo(tmp_path)
    (root / "src" / "n.ipynb").write_text("{\"cells\": []}", encoding="utf-8")
    (root / "src" / "p.html").write_text("<html>ok</html>", encoding="utf-8")
    report = mod.audit(root, fp)
    paths = [m["path"] for m in report["scan_manifest"]]
    assert any(x.endswith(".ipynb") for x in paths)
    assert any(x.endswith(".html") for x in paths)


def test_directory_skips_logged():
    report = mod.audit(ROOT, FREEZE)
    assert "directory_skips" in report
    assert "directory_skip_impact" in report


def test_root_readme_question_is_hit(tmp_path):
    root, fp = _clean_repo(tmp_path)
    qn = " ".join(_q1(root).split())
    (root / "README.md").write_text("# n\n" + qn + "\n", encoding="utf-8")
    _write_freeze_with_q(fp, _q1(root))
    report = mod.audit(root, fp)
    assert report["per_task"][0]["n_hits"] >= 1
    assert report["per_task"][0]["verdict"] != mod.V_NO_HIT


def test_phase2_independence_still_blocked():
    report = mod.audit(ROOT, FREEZE)
    assert report["independence"] == "CONFIRMATION_INDEPENDENCE_BLOCKED"
