"""Offline tests for RQ3 power-table helper (exact-test limits)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "scripts/level3_pilot_r4/rq3_power_tables.py"
spec = importlib.util.spec_from_file_location("rq3_power", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_exact_wilcoxon_min_p_table():
    assert mod.exact_wilcoxon_min_two_sided_p(1) == 1.0
    assert abs(mod.exact_wilcoxon_min_two_sided_p(5) - 0.0625) < 1e-12
    assert abs(mod.exact_wilcoxon_min_two_sided_p(6) - 0.03125) < 1e-12
    assert abs(mod.exact_wilcoxon_min_two_sided_p(10) - 2 / 1024) < 1e-12


def test_r5_cannot_reject_two_sided_alpha05():
    assert mod.can_reject_alpha05_exact_two_sided(5) is False
    assert mod.can_reject_alpha05_exact_two_sided(6) is True
    assert mod.can_reject_alpha05_exact_two_sided(10) is True


def test_sign_test_same_limit():
    assert abs(mod.binom_sign_test_min_two_sided_p(5) - 0.0625) < 1e-12


def test_normal_approx_positive():
    r = mod.normal_approx_R(0.05, 0.04)
    assert 4.0 < r < 6.0
    assert mod.normal_approx_R(0.0, 0.1) == float("inf")
