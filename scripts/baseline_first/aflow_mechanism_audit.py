"""Quantifiable search-mechanism audit via official AFlow code (0 real LLM).

Measures:
  - parent-selection distribution under controlled scores
  - experience dedup rejection (exact-string)
  - success/failure tagging
  - selection shift toward better parents
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AFLOW = ROOT / "external" / "AFlow"
try:
    import tree_sitter  # noqa
except Exception:
    import types
    ts = types.ModuleType("tree_sitter")
    ts.Node = object
    ts.Parser = object
    ts.Language = object
    sys.modules["tree_sitter"] = ts
sys.path.insert(0, str(AFLOW))

from scripts.optimizer_utils.data_utils import DataUtils
from scripts.optimizer_utils.experience_utils import ExperienceUtils


def audit_selection():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        du = DataUtils(td)
        # three parents: low / high / mid
        items = [
            {"round": 1, "score": 0.30},
            {"round": 2, "score": 0.90},
            {"round": 3, "score": 0.60},
        ]
        picks = []
        for _ in range(2000):
            picks.append(du.select_round(items)["round"])
        from collections import Counter

        c = Counter(picks)
        total = sum(c.values())
        probs = du._compute_probabilities([30, 90, 60])
        return {
            "empirical_selection_freq_2000": {str(k): v / total for k, v in sorted(c.items())},
            "theoretical_mixed_probs_sorted_desc": [float(x) for x in probs],
            "note": "sorted desc = [90,60,30] → probs align to those scores",
        }


def audit_experience_dedup():
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        eu = ExperienceUtils(td)
        rd = Path(td) / "round_1"
        rd.mkdir()
        (rd / "experience.json").write_text(json.dumps({
            "father node": 1, "modification": "add reflection",
            "before": 0.5, "after": 0.7, "succeed": True,
        }), encoding="utf-8")
        rd2 = Path(td) / "round_2"
        rd2.mkdir()
        (rd2 / "experience.json").write_text(json.dumps({
            "father node": 1, "modification": "add retry",
            "before": 0.5, "after": 0.4, "succeed": False,
        }), encoding="utf-8")
        proc = eu.load_experience(path=td, mode="custom")
        exp = eu.format_experience(proc, 1)
        return {
            "success_mod_blacklisted": eu.check_modification(proc, "add reflection", 1) is False,
            "failure_mod_blacklisted": eu.check_modification(proc, "add retry", 1) is False,
            "novel_mod_accepted": eu.check_modification(proc, "novel idea", 1) is True,
            "format_bans_successes_too": "Absolutely prohibit add reflection" in exp,
            "format_bans_failures": "Absolutely prohibit add retry" in exp,
        }


def main():
    result = {
        "selection_audit": audit_selection(),
        "experience_dedup_audit": audit_experience_dedup(),
        "quantifiable_behavior": True,
        "performance_impact_on_real_tasks": "NOT_ESTABLISHED (needs Level 3)",
    }
    print(json.dumps(result, indent=2))
    out = ROOT / "results" / "stage3_0_p1_r1"
    out.mkdir(parents=True, exist_ok=True)
    (out / "search_mechanism_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
