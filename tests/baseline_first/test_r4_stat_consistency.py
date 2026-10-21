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



def test_no_stale_f2_choice_language():
    for name in (
        "R4_R5_STATISTICAL_CONSISTENCY.md",
        "RQ3_MULTI_SEED_DESIGN.md",
        "PREREGISTRATION.md",
        "TASKSET_AND_STATISTICS.md",
        "RQ3_POWER_TABLES.txt",
    ):
        p = ROOT / "docs/level3_pilot_r4_design" / name
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        # active choice language must not remain
        assert "Choose F2-a" not in t
        assert "per option F2-a/b/c" not in t
        # IUT must be present in the main consistency doc
        if name == "R4_R5_STATISTICAL_CONSISTENCY.md":
            assert "IUT" in t
            assert "NOT used" in t or "SUPERSEDED" in t


def test_seed_contract_fixed_base():
    from src.research.r4_exec_freeze import BASE_SEED, DEFAULT_EXEC_FREEZE, canonical_config_sha256

    assert BASE_SEED == 20260601
    cfg = DEFAULT_EXEC_FREEZE
    assert cfg["seeds"]["base_seed"] == BASE_SEED
    assert cfg["mutation_plan"]["base_seed"] == BASE_SEED
    # tamper base and resync derived — still rejected
    import copy

    c2 = copy.deepcopy(cfg)
    c2["seeds"]["base_seed"] = 999
    c2["mutation_plan"]["base_seed"] = 999
    c2["seeds"]["plan_seeds"] = {"6": 999 + 1009 * 6, "10": 999 + 1009 * 10}
    c2["config_sha256"] = canonical_config_sha256(c2)
    from src.research.r4_exec_freeze import verify_exec_config_structure

    assert verify_exec_config_structure(c2) == "EXEC_SEEDS_BASE_MISMATCH"


def test_r_values_must_be_true_ints():
    import copy

    from src.research.r4_exec_freeze import DEFAULT_EXEC_FREEZE, canonical_config_sha256, verify_exec_config_structure

    for bad in (True, "6", 6.0, 6.9):
        c = copy.deepcopy(DEFAULT_EXEC_FREEZE)
        c["budget_caps"]["planned_r_values"] = [bad, 10] if bad != 10 else [6, bad]
        c["config_sha256"] = canonical_config_sha256(c)
        err = verify_exec_config_structure(c)
        assert err.startswith("BUDGET_R_NOT_INT") or err.startswith("BUDGET_PLANNED_R"), (bad, err)



def test_v2_freeze_has_no_execution_flag_and_valid_structure():
    import json as _json

    from src.research.r4_exec_freeze import verify_exec_config_structure

    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v2_proposed.json"
    cfg = _json.loads(p.read_text(encoding="utf-8"))
    assert "execution_authorized" not in cfg
    assert verify_exec_config_structure(cfg) == ""
    assert cfg["config_sha256"]
    # recompute
    from src.research.r4_exec_freeze import canonical_config_sha256

    assert canonical_config_sha256(cfg) == cfg["config_sha256"]


def test_v2_rq3_iut_consistency():
    import json as _json

    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v2_proposed.json"
    cfg = _json.loads(p.read_text(encoding="utf-8"))
    ep = cfg["endpoints"]
    rq3 = ep["rq3_comparisons"]
    assert rq3["E-D"]["role"] == "co-primary"
    assert rq3["E-C"]["role"] == "co-primary"
    assert rq3.get("multiplicity") == "IUT"
    assert "iut" in rq3["claim_rule"].lower()
    assert "Holm(2) on F2" in ep.get("holm_note", "") or "No Holm(2)" in ep.get("holm_note", "")
    assert "E-D" in ep["primary"] or "E−D" in ep["primary"]


def test_no_active_holm2_alternative_in_freeze():
    import json as _json

    p = ROOT / "docs/level3_pilot_r4_design/execution_freeze_v2_proposed.json"
    raw = p.read_text(encoding="utf-8")
    assert "with Holm(2) if both are co-primary" not in raw


def test_seed_type_attacks():
    import copy

    from src.research.r4_exec_freeze import (
        BASE_SEED,
        DEFAULT_EXEC_FREEZE,
        canonical_config_sha256,
        verify_exec_config_structure,
    )

    for bad in (20260601.0, True, "20260601"):
        cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
        cfg["seeds"]["base_seed"] = bad
        cfg["mutation_plan"]["base_seed"] = bad if not isinstance(bad, str) else int(bad) if str(bad).isdigit() else bad
        cfg["config_sha256"] = canonical_config_sha256(cfg)
        err = verify_exec_config_structure(cfg)
        assert err.startswith("EXEC_SEEDS"), (bad, err)


def test_plan_seed_key_semantics():
    import copy

    from src.research.r4_exec_freeze import (
        DEFAULT_EXEC_FREEZE,
        canonical_config_sha256,
        verify_exec_config_structure,
    )

    cfg = copy.deepcopy(DEFAULT_EXEC_FREEZE)
    # non-canonical key
    cfg["seeds"]["plan_seeds"] = {"06": cfg["seeds"]["plan_seeds"]["6"], "10": cfg["seeds"]["plan_seeds"]["10"]}
    cfg["config_sha256"] = canonical_config_sha256(cfg)
    err = verify_exec_config_structure(cfg)
    assert err.startswith("EXEC_SEEDS") or err.startswith("BUDGET_PLANNED_R")
