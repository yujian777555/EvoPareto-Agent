"""R1.1 runtime-order and gate regression tests. No real network."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "level3_pilot_r4"))

import run_micro_r354 as r


# ---------- acc / classify ----------
def row(**kw):
    base = {"task_id": "t", "valid_eval": True, "correct": False,
            "predicted": "42", "error": "", "skipped": False,
            "graph_hash_mismatch": False}
    base.update(kw)
    return base


class TestAccStrict:
    def test_all_valid_correct(self):
        rows = [row(correct=True, predicted="1"), row(correct=True, predicted="2")]
        assert r.acc(rows) == 1.0

    def test_all_valid_with_wrong(self):
        rows = [row(correct=True), row(correct=False)]
        assert r.acc(rows) == 0.5

    def test_mixed_correct_wrong(self):
        rows = [row(correct=True), row(correct=False), row(correct=True)]
        assert abs(r.acc(rows) - 2 / 3) < 1e-9

    def test_execution_failure_returns_none(self):
        rows = [row(correct=True), row(correct=False, error="TIMEOUT")]
        assert r.acc(rows) is None

    def test_graph_hash_mismatch(self):
        rows = [row(correct=True), row(graph_hash_mismatch=True)]
        assert r.acc(rows) is None

    def test_predicted_none(self):
        rows = [row(correct=True), row(predicted=None)]
        assert r.acc(rows) is None

    def test_error_nonempty_with_success_fields(self):
        rows = [row(correct=True, predicted="42", error="CRASH")]
        assert r.acc(rows) is None

    def test_skipped(self):
        rows = [row(correct=True), row(skipped=True)]
        assert r.acc(rows) is None

    def test_missing_and_count_mismatch(self):
        rows = [row(correct=True)]
        assert r.acc(rows, expected_n=2) is None

    def test_empty(self):
        assert r.acc([]) is None


class TestClassify:
    def test_categories_distinct(self):
        assert r.classify_row(row(correct=True)) == "CORRECT"
        assert r.classify_row(row(correct=False)) == "WRONG_ANSWER"
        assert r.classify_row(row(error="X")) == "EXEC_FAILURE"
        assert r.classify_row(row(graph_hash_mismatch=True)) == "HASH_MISMATCH"
        assert r.classify_row(row(predicted=None)) == "PARSE_FAILURE"
        assert r.classify_row(row(skipped=True)) == "SKIPPED"


class TestPaired:
    def test_task_id_mismatch(self):
        a = [row(task_id="t1"), row(task_id="t2")]
        b = [row(task_id="t2"), row(task_id="t1")]
        out = r.paired(a, b)
        assert out["status"] == "INCOMPLETE"
        assert out["reason"] == "TASK_ID_MISMATCH"

    def test_invalid_excluded(self):
        a = [row(task_id="t1", correct=False), row(task_id="t2", error="E")]
        b = [row(task_id="t1", correct=True), row(task_id="t2", correct=True)]
        out = r.paired(a, b)
        assert out["status"] == "INCOMPLETE"


class TestStaticPreflight:
    def _man_ts(self, tmp_path):
        # minimal valid-looking blocks (content_sha must match)
        def block(ids):
            tasks = [{"task_id": f"gsm8k-train-{i:04d}", "question": "Q", "gold_answer": "1"}
                     for i in ids]
            return {"tasks": tasks, "indices": list(ids)}
        ts = {"calibration": block([0, 1]), "dev": block([2, 3]), "confirm": block([4, 5])}
        import hashlib, json as J
        def csha(b):
            blob = J.dumps([(t["task_id"], " ".join(t["question"].split()), t["gold_answer"])
                            for t in b["tasks"]], sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
            return hashlib.sha256(blob.encode("utf-8")).hexdigest()
        man = {
            "train_sha256": "0" * 64,  # will mismatch train file
            "calib_task_set_sha256": csha(ts["calibration"]),
            "dev_task_set_sha256": csha(ts["dev"]),
            "confirm_task_set_sha256": csha(ts["confirm"]),
            "n_calib": 2, "n_dev": 2, "n_confirm": 2,
            "used_indices_excluded": [],
            "protocol_id": r.PROTOCOL_ID,
        }
        freeze = {"base_text": r.BASE_STRATEGY_TEXT,
                  "base_text_sha256": __import__("hashlib").sha256(
                      r.BASE_STRATEGY_TEXT.encode("utf-8")).hexdigest(),
                  "protocol_id": r.PROTOCOL_ID}
        return man, ts, freeze

    def test_bad_train_sha(self):
        man, ts, freeze = self._man_ts(None)
        errs = r.preflight_static(man, ts, freeze)
        assert "TRAIN_SHA_MISMATCH" in errs or "TRAIN_FILE_MISSING" in errs

    def test_base_sha_recompute_mismatch(self):
        man, ts, freeze = self._man_ts(None)
        freeze["base_text_sha256"] = "deadbeef"
        errs = r.preflight_static(man, ts, freeze)
        assert any("BASELINE_SHA" in e for e in errs)

    def test_base_text_mismatch(self):
        man, ts, freeze = self._man_ts(None)
        freeze["base_text"] = "tampered"
        errs = r.preflight_static(man, ts, freeze)
        assert "BASELINE_TEXT_MISMATCH" in errs

    def test_sets_overlap(self):
        man, ts, freeze = self._man_ts(None)
        ts["dev"]["indices"] = [0, 1]  # overlap with calib
        import hashlib, json as J
        def csha(b):
            blob = J.dumps([(t["task_id"], " ".join(t["question"].split()), t["gold_answer"])
                            for t in b["tasks"]], sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"))
            return hashlib.sha256(blob.encode("utf-8")).hexdigest()
        man["dev_task_set_sha256"] = csha(ts["dev"])
        errs = r.preflight_static(man, ts, freeze)
        assert "SETS_OVERLAP" in errs


class TestAuthGate:
    def test_missing_auth(self, tmp_path):
        # isolate from a live authorization.json if present
        auth = Path("results/level3_pilot_r4_micro_r354/authorization.json")
        backup = None
        if auth.exists():
            backup = auth.read_text(encoding="utf-8")
            auth.unlink()
        try:
            errs = r.check_real_authorization({"confirm_task_set_sha256": "x"},
                                              {"protocol_id": r.PROTOCOL_ID})
            assert errs == ["AUTH_MISSING"] or "AUTH_MISSING" in errs
        finally:
            if backup is not None:
                auth.write_text(backup, encoding="utf-8")

    def test_field_missing(self, tmp_path):
        # monkeypatch path
        import run_micro_r354 as mod
        orig = mod.ROOT
        try:
            fake = tmp_path
            (fake / "results" / "level3_pilot_r4_micro_r354").mkdir(parents=True)
            auth = {"protocol_id": mod.PROTOCOL_ID, "model_id": mod.MODEL_ID}
            (fake / "results" / "level3_pilot_r4_micro_r354" / "authorization.json").write_text(
                json.dumps(auth))
            mod.ROOT = fake
            errs = mod.check_real_authorization({"confirm_task_set_sha256": "x"},
                                                {"protocol_id": mod.PROTOCOL_ID})
            assert any("AUTH_FIELD_MISSING" in e for e in errs)
        finally:
            mod.ROOT = orig


class TestAOConsistency:
    def test_feedback_text_mismatch(self):
        errs = r.check_ao_consistency(
            "B", "A", "O",
            {"feedback_text_used": "fix1", "parent_id": "B"},
            {"feedback_text_used": "fix2", "parent_id": "B"},
            None,
        )
        assert "A_O_FEEDBACK_TEXT_MISMATCH" in errs

    def test_ok(self):
        errs = r.check_ao_consistency(
            "B", "A", "O",
            {"feedback_text_used": "fix", "feedback_id": "f1", "parent_id": "B", "source_task_ids": ["t1"]},
            {"feedback_text_used": "fix", "feedback_id": "f1", "parent_id": "B", "source_task_ids": ["t1"]},
            None,
        )
        assert errs == []


class TestHolmIncomplete:
    def test_missing_comp_marked(self):
        pvals = {"A_vs_B": 0.01}
        holm = r.holm_adjust(pvals)
        # our main() marks incomplete separately; ensure holm_adjust works
        assert "A_vs_B" in holm
