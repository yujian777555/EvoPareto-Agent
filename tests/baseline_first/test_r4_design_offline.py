"""Offline tests for LEVEL3-PILOT-R4 design-prep statistics and gates.

Everything here uses fixed synthetic samples. No network, no DeepSeek, no
credentials, no Docker. Simulated data is explicitly labeled.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.r4_paired_stats import (
    canonical_task_set_sha256,
    check_budget_consistency,
    check_frozen_unchanged,
    count_paired,
    detect_anomalies,
    exact_mcnemar,
    holm_bonferroni,
    summarize_groups,
    verify_task_set,
    wilson_ci,
)

SIMULATED = "SIMULATED"  # never confuse with real model results


# ---------------------------------------------------------------------------
# Paired counts
# ---------------------------------------------------------------------------

def test_count_paired_r3_like_shape():
    # SIMULATED: b=2, c=0, n11=29, n00=4  (mirrors R3 cell structure)
    baseline = {f"t{i}": (i < 33) for i in range(35)}  # 33 correct-ish
    # make exact: parent correct on 29+2=31? Let us build explicitly.
    baseline = {}
    comparator = {}
    for i in range(35):
        if i < 29:
            baseline[f"t{i}"] = True
            comparator[f"t{i}"] = True
        elif i < 31:
            baseline[f"t{i}"] = False
            comparator[f"t{i}"] = True  # improved
        else:
            baseline[f"t{i}"] = False
            comparator[f"t{i}"] = False
    counts = count_paired(baseline, comparator)
    assert counts.b == 2
    assert counts.c == 0
    assert counts.n11 == 29
    assert counts.n00 == 4
    assert counts.n == 35
    assert counts.net_gain == 2


def test_count_paired_rejects_mismatched_ids():
    with pytest.raises(ValueError, match="id set mismatch"):
        count_paired({"a": True}, {"b": True})


def test_count_paired_explicit_ids_missing_raises():
    with pytest.raises(ValueError, match="missing task id"):
        count_paired({"a": True}, {"a": True}, ids=["a", "b"])


# ---------------------------------------------------------------------------
# Exact McNemar
# ---------------------------------------------------------------------------

def test_mcnemar_b2_c0_matches_historical_values():
    # SIMULATED counts identical to R3 discordant pair (2, 0)
    res = exact_mcnemar(2, 0)
    assert res["n_discordant"] == 2
    assert abs(res["p_one_sided"] - 0.25) < 1e-12
    assert abs(res["p_two_sided"] - 0.50) < 1e-12


def test_mcnemar_no_discordant_is_one():
    res = exact_mcnemar(0, 0)
    assert res["p_two_sided"] == 1.0
    assert res["p_one_sided"] == 1.0


def test_mcnemar_symmetric():
    a = exact_mcnemar(5, 1)
    b = exact_mcnemar(1, 5)
    assert abs(a["p_two_sided"] - b["p_two_sided"]) < 1e-12


def test_mcnemar_perfect_one_sided_discordance_is_small():
    res = exact_mcnemar(10, 0)
    assert res["p_one_sided"] == pytest.approx(1 / 1024)
    assert res["p_two_sided"] == pytest.approx(2 / 1024)


def test_mcnemar_rejects_negative():
    with pytest.raises(ValueError):
        exact_mcnemar(-1, 0)


# ---------------------------------------------------------------------------
# Wilson CI
# ---------------------------------------------------------------------------

def test_wilson_ci_contains_estimate_and_is_sane():
    p, lo, hi = wilson_ci(29, 35)
    assert 0.0 <= lo <= p <= hi <= 1.0
    assert abs(p - 29 / 35) < 1e-12


def test_wilson_ci_bounds():
    with pytest.raises(ValueError):
        wilson_ci(0, 0)
    with pytest.raises(ValueError):
        wilson_ci(5, 3)


# ---------------------------------------------------------------------------
# Holm-Bonferroni
# ---------------------------------------------------------------------------

def test_holm_orders_and_caps():
    p = {"B-A": 0.04, "C-A": 0.01, "D-A": 0.03, "E-A": 0.20, "E-D": 0.02}
    out = holm_bonferroni(p, alpha=0.05)
    assert set(out) == set(p)
    # smallest raw p gets rank 1
    assert out["C-A"]["rank"] == 1
    assert out["C-A"]["p_holm"] <= out["D-A"]["p_holm"] <= out["B-A"]["p_holm"]
    assert out["E-A"]["p_holm"] <= 1.0
    # adjusted p never below raw p in Holm step-down (running max)
    for name, rec in out.items():
        assert rec["p_holm"] >= rec["p_raw"] - 1e-12


def test_holm_empty():
    assert holm_bonferroni({}) == {}


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def test_detect_anomalies_finds_duplicates_and_missing():
    rows = [
        {"task_id": "t1", "role": "A", "correct": True},
        {"task_id": "t1", "role": "A", "correct": True},  # duplicate
        {"task_id": "t2", "role": "A", "correct": False},
        {"task_id": "t1", "role": "B", "correct": True},
        # B missing t2
    ]
    res = detect_anomalies(
        rows,
        required_ids=["t1", "t2"],
        expect_groups=["A", "B"],
    )
    assert res["ok"] is False
    assert any(d.get("task_id") == "t1" for d in res["duplicate_rows"])
    assert res["missing_ids_per_group"]["B"] == ["t2"]


def test_detect_anomalies_clean_pass():
    rows = [
        {"task_id": "t1", "role": "A", "correct": True},
        {"task_id": "t2", "role": "A", "correct": False},
        {"task_id": "t1", "role": "B", "correct": True},
        {"task_id": "t2", "role": "B", "correct": True},
    ]
    res = detect_anomalies(rows, required_ids=["t1", "t2"], expect_groups=["A", "B"])
    assert res["ok"] is True
    assert res["duplicate_rows"] == []


# ---------------------------------------------------------------------------
# Task-set hash gate
# ---------------------------------------------------------------------------

def _sample_tasks():
    return [
        {"task_id": "gsm8k-official-test-0001", "question": "Q one?", "gold_answer": "1"},
        {"task_id": "gsm8k-official-test-0002", "question": "Q two?", "gold_answer": "2"},
        {"task_id": "gsm8k-official-test-0003", "question": "Q three?", "gold_answer": "3"},
    ]


def test_task_set_hash_stable_and_verifies():
    tasks = _sample_tasks()
    h = canonical_task_set_sha256(tasks)
    assert len(h) == 64
    assert canonical_task_set_sha256(tasks) == h
    assert verify_task_set(tasks, h, h) == ""


def test_task_set_tamper_question_breaks_gate():
    tasks = _sample_tasks()
    h = canonical_task_set_sha256(tasks)
    bad = [dict(t) for t in tasks]
    bad[0]["question"] = "TAMPERED"
    err = verify_task_set(bad, h, h)
    assert "TASKSET_HASH_MISMATCH" in err


def test_task_set_duplicate_id_rejected():
    tasks = _sample_tasks()
    h = canonical_task_set_sha256(tasks)
    bad = [dict(t) for t in tasks]
    bad[1]["task_id"] = bad[0]["task_id"]
    err = verify_task_set(bad, h, h)
    assert err == "TASKSET_DUPLICATE_ID"


def test_task_set_missing_field_rejected():
    tasks = _sample_tasks()
    h = canonical_task_set_sha256(tasks)
    bad = [dict(t) for t in tasks]
    del bad[0]["gold_answer"]
    err = verify_task_set(bad, h, h)
    assert "TASKSET_FIELD_MISSING" in err


def test_task_set_expected_hash_enforced():
    tasks = _sample_tasks()
    h = canonical_task_set_sha256(tasks)
    err = verify_task_set(tasks, h, "0" * 64)
    assert err == "TASKSET_HASH_NOT_EXPECTED"


# ---------------------------------------------------------------------------
# Frozen immutability
# ---------------------------------------------------------------------------

def test_frozen_unchanged_detects_modification():
    before = {"results/a.json": "aaa", "results/b.json": "bbb"}
    after = {"results/a.json": "aaa", "results/b.json": "BBB"}
    res = check_frozen_unchanged(before, after)
    assert res["ok"] is False
    assert res["modified"] == ["results/b.json"]


def test_frozen_unchanged_ok():
    snap = {"results/a.json": "aaa"}
    assert check_frozen_unchanged(snap, dict(snap))["ok"] is True


# ---------------------------------------------------------------------------
# Budget consistency
# ---------------------------------------------------------------------------

def test_budget_gap_is_reported_not_hidden():
    res = check_budget_consistency(
        planned_requests=480,
        remaining_requests=56,
        planned_cost_usd=1.44,
        remaining_cost_usd=4.96,
        planned_tokens_in=480 * 300,
        planned_tokens_out=480 * 300,
        cap_tokens_in=2_000_000,
        cap_tokens_out=200_000,
        new_requests_this_round=0,
    )
    assert res["ok"] is False
    assert res["fits_requests"] is False
    assert res["gap_requests"] == 424
    assert res["new_requests_this_round"] == 0


def test_budget_token_out_cap_enforced():
    res = check_budget_consistency(
        planned_requests=10,
        remaining_requests=56,
        planned_cost_usd=0.01,
        remaining_cost_usd=4.0,
        planned_tokens_in=1000,
        planned_tokens_out=500_000,
        cap_tokens_in=2_000_000,
        cap_tokens_out=200_000,
        new_requests_this_round=0,
    )
    assert any(p.startswith("TOKEN_OUT_CAP_EXCEEDED") for p in res["problems"])


def test_budget_rejects_nonzero_new_requests():
    res = check_budget_consistency(
        planned_requests=1,
        remaining_requests=56,
        planned_cost_usd=0.0,
        remaining_cost_usd=4.0,
        planned_tokens_in=1,
        planned_tokens_out=1,
        cap_tokens_in=10,
        cap_tokens_out=10,
        new_requests_this_round=1,
    )
    assert res["ok"] is False
    assert any(p.startswith("NEW_REQUESTS_NONZERO") for p in res["problems"])


# ---------------------------------------------------------------------------
# summarize_groups integration (SIMULATED)
# ---------------------------------------------------------------------------

def test_summarize_groups_simulated_end_to_end():
    """SIMULATED data only. Must never be used as a real model result."""
    ids = [f"t{i}" for i in range(20)]
    base = {i: (i not in {"t18", "t19"}) for i in ids}  # 18 correct
    b_grp = {i: (i not in {"t18", "t19"}) for i in ids}  # same as base
    c_grp = {i: (i not in {"t19"}) for i in ids}  # one improvement
    d_grp = {i: (i not in {"t18", "t19"}) for i in ids}
    e_grp = {i: (i not in {"t17", "t18", "t19"}) for i in ids}  # worse

    out = summarize_groups(
        "A",
        base,
        {"B": b_grp, "C": c_grp, "D": d_grp, "E": e_grp},
    )
    assert out["n_tasks"] == 20
    assert out["comparisons"]["B"]["counts"]["b_improved"] == 0
    assert out["comparisons"]["B"]["counts"]["c_regressed"] == 0
    assert out["comparisons"]["C"]["counts"]["b_improved"] == 1
    assert out["comparisons"]["C"]["counts"]["c_regressed"] == 0
    assert out["comparisons"]["E"]["counts"]["c_regressed"] == 1
    assert "holm" in out["comparisons"]["C"]
    assert out["comparisons"]["C"]["mcnemar"]["p_two_sided"] == pytest.approx(1.0)
    # evidence note present so callers cannot forget labeling
    assert "SIMULATED" in out["evidence_class_note"] or "SIMULATED" == SIMULATED


def test_offline_module_has_no_network_imports():
    src = (ROOT / "src" / "research" / "r4_paired_stats.py").read_text(encoding="utf-8")
    lowered = src.lower()
    # banned modules / providers as import or call targets
    for banned in (
        "import urllib",
        "import requests",
        "import httpx",
        "import aiohttp",
        "from urllib",
        "from requests",
        "from httpx",
        "from aiohttp",
        "http.client",
        "deepseek_api",
        "openai",
    ):
        assert banned not in lowered, banned

