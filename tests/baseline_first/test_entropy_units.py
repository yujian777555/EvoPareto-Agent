"""Entropy / effective-parent math unit test (Stage 3.0-P1-R2A-R1 Task 1).

Ensures selection entropy uses bits (log2), excludes initial no-father nodes,
and that effective parent count equals 2**H_bits.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def test_entropy_bits_formula():
    freq = [1, 1, 3, 2, 9, 1, 7]
    total = sum(freq)
    freqs = [c / total for c in freq]
    H_bits = -sum(p * math.log2(p) for p in freqs if p > 0)
    eff = 2.0 ** H_bits
    assert abs(H_bits - 2.29597512699001) < 1e-9
    assert abs(eff - 4.910858068512094) < 1e-9


def test_effective_count_matches_nats_form():
    # e^H_nats must equal 2^H_bits (same effective number)
    freq = [1, 1, 3, 2, 9, 1, 7]
    total = sum(freq)
    freqs = [c / total for c in freq]
    H_nats = -sum(p * math.log(p) for p in freqs if p > 0)
    H_bits = -sum(p * math.log2(p) for p in freqs if p > 0)
    assert abs(math.exp(H_nats) - 2.0 ** H_bits) < 1e-9


def test_gsm8k_graphs_excludes_initial_and_uses_bits():
    res = ROOT / "results" / "stage3_0_p1_r2a" / "lineage_metrics.json"
    data = json.loads(res.read_text(encoding="utf-8"))
    g = data["per_variant"]["GSM8K/graphs"]
    assert g["n_children_with_father"] == 24
    assert g["n_initial_no_father"] == 1
    assert "None" not in g["parent_selection_frequency"]
    assert abs(g["selection_entropy_bits"] - 2.296) < 0.01
    assert abs(g["effective_parent_count"] - 4.91) < 0.02
    assert abs(g["lineage_concentration_top2_share"] - 0.6667) < 0.001
    assert g["entropy_unit"].startswith("bits")
    assert g["effective_parent_count_formula"] == "2 ** H_bits"


def test_analysis_script_recomputes_same_values():
    sys.path.insert(0, str(ROOT / "scripts" / "baseline_first"))
    import importlib

    mod = importlib.import_module("r2a_full_analysis")
    rows = mod.load_rows()
    lineage, _ = mod.task_d(rows)
    g = lineage["GSM8K/graphs"]
    assert g["n_children_with_father"] == 24
    assert abs(g["selection_entropy_bits"] - 2.29597512699001) < 1e-9
    assert abs(g["effective_parent_count"] - 4.910858068512094) < 1e-9
