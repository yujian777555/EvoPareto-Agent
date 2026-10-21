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


def test_exec_freeze_v1_rq3_requires_both_comparisons():
    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v1_proposed.json"
    cfg = json.loads(p.read_text(encoding="utf-8"))
    ep = cfg["endpoints"]
    assert "E-D" in ep["rq3_comparisons"]
    assert "E-C" in ep["rq3_comparisons"]
    assert ep["rq3_comparisons"]["E-D"]["role"] == "co-primary"
    assert ep["rq3_comparisons"]["E-C"]["role"] == "co-primary"
    assert "both" in ep["rq3_comparisons"]["claim_rule"].lower()


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
