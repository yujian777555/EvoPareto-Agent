"""RQ3 statistical protocol consistency checks (offline, no model calls)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_statistical_consistency_doc_exists():
    p = ROOT / "docs/level3_pilot_r4_design/R4_R5_STATISTICAL_CONSISTENCY.md"
    assert p.exists()
    t = p.read_text(encoding="utf-8")
    assert "E − D" in t or "E−D" in t
    assert "E − C" in t or "E−C" in t
    assert "PROPOSED" in t


def test_exec_freeze_v2_rq3_iut_both_comparisons():
    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v2_proposed.json"
    if not p.exists():
        import pytest
        pytest.skip("v2 freeze absent")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    ep = cfg["endpoints"]
    assert "E-D" in ep["rq3_comparisons"]
    assert "E-C" in ep["rq3_comparisons"]
    assert ep["rq3_comparisons"]["E-D"]["role"] == "co-primary"
    assert ep["rq3_comparisons"]["E-C"]["role"] == "co-primary"
    assert "iut" in ep["rq3_comparisons"]["claim_rule"].lower()
    assert ep["rq3_comparisons"].get("multiplicity") == "IUT"
    assert "E-D" in ep["primary"] or "E−D" in ep["primary"] or "E-D" in ep["primary"]


def test_holm_family_task_level_only_documented():
    p = ROOT / "docs/level3_pilot_r4_design/R4_R5_STATISTICAL_CONSISTENCY.md"
    t = p.read_text(encoding="utf-8")
    assert "task-level" in t.lower()
    assert "0.01" in t  # Holm(5) step-1 threshold documented
    assert "0.03125" in t or "R≥6" in t or "R>=6" in t


def test_rq3_power_tables_reject_r5():
    from src.research.r4_exec_freeze import compute_budget_requirements
    # power table script
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rq3_power", ROOT / "scripts/level3_pilot_r4/rq3_power_tables.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    assert mod.can_reject_alpha05_exact_two_sided(5) is False
    assert mod.can_reject_alpha05_exact_two_sided(6) is True



def test_iut_not_holm2_in_docs():
    p = ROOT / "docs/level3_pilot_r4_design/R4_R5_STATISTICAL_CONSISTENCY.md"
    t = p.read_text(encoding="utf-8")
    assert "IUT" in t
    assert "NOT used on F2" in t or "not** applied on F2" in t or "Holm(2) is **not**" in t


def test_r6_n_eff_power_note():
    p = ROOT / "docs/level3_pilot_r4_design/RQ3_POWER_TABLES.txt"
    t = p.read_text(encoding="utf-8")
    assert "IUT" in t
    assert "not sufficient" in t.lower() or "necessary" in t.lower()


def test_wilcoxon_min_p_uses_nonzero_n():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "rq3_power", ROOT / "scripts/level3_pilot_r4/rq3_power_tables.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    # if only 4 nonzero pairs, min two-sided p = 2/16 = 0.125 > 0.05
    assert abs(mod.exact_wilcoxon_min_two_sided_p(4) - 0.125) < 1e-12
    assert mod.can_reject_alpha05_exact_two_sided(4) is False
    assert mod.can_reject_alpha05_exact_two_sided(6) is True
