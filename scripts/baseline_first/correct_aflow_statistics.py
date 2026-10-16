"""Corrected AFlow history statistics (Stage 3.0-P1-R2A).

Fixes vs prior analyze_aflow_history.py:
  - dataset grouping (SEARCH_MAIN / SEARCH_ABLATION / TEST_ONLY / INITIAL)
  - proper denominators: comparable mutations only (before&after present)
  - succeed-flag vs score-delta discrepancy enumerated per record
  - lineage: successful-child reselection (child later becomes father)
  - duplicate metrics: groups / extra occurrences / same-parent / cross-parent
  - stable SHA-256 identity (no builtin hash())
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "external" / "AFlow_results" / "results"
OUT = ROOT / "results" / "stage3_0_p1_r2a"
OUT.mkdir(parents=True, exist_ok=True)

TOL = 1e-9

def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def classify_variant(variant: str, round_no: int) -> str:
    if "ablation" in variant:
        return "SEARCH_ABLATION"
    if variant == "graphs_test":
        return "TEST_ONLY"
    if round_no <= 1:
        return "INITIAL_WORKFLOW"
    return "SEARCH_MAIN"


def load_variants():
    rows = []
    for bench in sorted(BASE.iterdir()):
        if not bench.is_dir():
            continue
        for var in sorted(bench.iterdir()):
            if not var.is_dir():
                continue
            for rd in sorted(var.glob("round_*"), key=lambda p: int(p.name.split("_")[1])):
                n = int(rd.name.split("_")[1])
                exp = {}
                ep = rd / "experience.json"
                if ep.exists() and ep.stat().st_size > 0:
                    try:
                        exp = json.loads(ep.read_text(encoding="utf-8"))
                    except Exception:
                        exp = {}
                graph = (rd / "graph.py").read_text(encoding="utf-8") if (rd / "graph.py").exists() else ""
                before = exp.get("before")
                after = exp.get("after")
                delta = (after - before) if (before is not None and after is not None) else None
                rows.append({
                    "benchmark": bench.name,
                    "variant": var.name,
                    "group": classify_variant(var.name, n),
                    "round": n,
                    "father": exp.get("father node"),
                    "modification": exp.get("modification"),
                    "before": before,
                    "after": after,
                    "delta": delta,
                    "succeed_flag": exp.get("succeed"),
                    "graph_sha": sha(graph),
                    "exp_path": str(ep.relative_to(BASE)) if ep.exists() else "",
                })
    return rows


def main():
    rows = load_variants()
    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)

    # ---- A2: correct rates ----
    def rates(subset, label):
        comparable = [r for r in subset if r["delta"] is not None]
        ups = sum(1 for r in comparable if r["delta"] > TOL)
        downs = sum(1 for r in comparable if r["delta"] < -TOL)
        ties = sum(1 for r in comparable if abs(r["delta"]) <= TOL)
        succ = sum(1 for r in subset if r["succeed_flag"] is True)
        missing = sum(1 for r in subset if r["delta"] is None)
        deltas = [r["delta"] for r in comparable]
        sd = sorted(deltas)
        med = sd[len(sd) // 2] if sd else None
        return {
            "label": label,
            "n_rounds": len(subset),
            "n_initial_rounds": sum(1 for r in subset if r["group"] == "INITIAL_WORKFLOW"),
            "n_comparable_mutations": len(comparable),
            "n_succeed_true": succ,
            "n_score_upgrades": ups,
            "n_score_downgrades": downs,
            "n_score_ties": ties,
            "n_missing_comparisons": missing,
            "succeed_flag_rate": succ / len(subset) if subset else 0,
            "paired_upgrade_rate": ups / len(comparable) if comparable else 0,
            "paired_downgrade_rate": downs / len(comparable) if comparable else 0,
            "tie_rate": ties / len(comparable) if comparable else 0,
            "mean_delta": sum(deltas) / len(deltas) if deltas else None,
            "median_delta": med,
        }

    stats = {"ALL": rates(rows, "ALL")}
    for gname in ("SEARCH_MAIN", "SEARCH_ABLATION", "TEST_ONLY", "INITIAL_WORKFLOW"):
        if gname in by_group:
            stats[gname] = rates(by_group[gname], gname)
    for bench in sorted({r["benchmark"] for r in rows}):
        stats[f"BENCH:{bench}"] = rates([r for r in rows if r["benchmark"] == bench], bench)

    # ---- A3: discrepancy succeed_flag vs delta ----
    discrep = []
    for r in rows:
        if r["succeed_flag"] is True and (r["delta"] is None or r["delta"] <= TOL):
            discrep.append({**{k: r[k] for k in ("benchmark","variant","round","exp_path","father","before","after","succeed_flag","delta")},
                            "classification": "SUCCEED_TRUE_BUT_NOT_UPGRADE"})
        if r["succeed_flag"] is not True and r["delta"] is not None and r["delta"] > TOL:
            discrep.append({**{k: r[k] for k in ("benchmark","variant","round","exp_path","father","before","after","succeed_flag","delta")},
                            "classification": "UPGRADE_BUT_FLAG_NOT_TRUE"})
    # summary of causes
    causes = Counter()
    for d in discrep:
        if d["after"] is None:
            causes["missing_after"] += 1
        elif d["before"] is None:
            causes["missing_before"] += 1
        elif d["delta"] is not None and abs(d["delta"]) <= TOL:
            causes["zero_delta_flagged_succeed"] += 1
        elif d["succeed_flag"] is not True:
            causes["delta_positive_but_flag_false"] += 1
        else:
            causes["other"] += 1

    # ---- B: lineage of successful children ----
    # successful mutation creates child C at round r; does C's round later
    # appear as father of other rounds (reselection)?
    rounds_by_key = {}
    for r in rows:
        rounds_by_key[(r["benchmark"], r["variant"], r["round"])] = r
    succ_children = [r for r in rows if r["succeed_flag"] is True]
    reselected = 0
    offspring_counts = []
    for c in succ_children:
        kids = [r for r in rows
                if r["benchmark"] == c["benchmark"] and r["variant"] == c["variant"]
                and r["father"] == c["round"] and r["round"] != c["round"]]
        offspring_counts.append(len(kids))
        if kids:
            reselected += 1
    # control: same for fail children
    fail_children = [r for r in rows if r["succeed_flag"] is False]
    fail_reselected = 0
    fail_offspring = []
    for c in fail_children:
        kids = [r for r in rows
                if r["benchmark"] == c["benchmark"] and r["variant"] == c["variant"]
                and r["father"] == c["round"] and r["round"] != c["round"]]
        fail_offspring.append(len(kids))
        if kids:
            fail_reselected += 1
    inherit = {
        "n_success_children": len(succ_children),
        "successful_child_reselection_rate": reselected / len(succ_children) if succ_children else 0,
        "successful_child_offspring_mean": sum(offspring_counts) / len(offspring_counts) if offspring_counts else 0,
        "n_fail_children": len(fail_children),
        "fail_child_reselection_rate": fail_reselected / len(fail_children) if fail_children else 0,
        "fail_child_offspring_mean": sum(fail_offspring) / len(fail_offspring) if fail_offspring else 0,
        "behavioral_inheritance": "BEHAVIORAL_INHERITANCE_NOT_ESTABLISHED",
        "note": "reselection = child round later appears as father; not proof of capability retention",
    }

    # ---- C: duplicate modification metrics ----
    mod_map = defaultdict(list)
    for r in rows:
        if r["modification"]:
            mod_map[r["modification"]].append(r)
    dup_groups = []
    extra_occ = 0
    same_parent = 0
    cross_parent = 0
    cross_run = 0
    for mod, recs in mod_map.items():
        if len(recs) > 1:
            extra_occ += len(recs) - 1
            parents = {str(x["father"]) for x in recs}
            runs = {(x["benchmark"], x["variant"]) for x in recs}
            if len(parents) == 1:
                same_parent += len(recs) - 1
            else:
                cross_parent += len(recs) - 1
            if len(runs) > 1:
                cross_run += len(recs) - 1
            dup_groups.append({
                "modification": mod[:120],
                "n_occurrences": len(recs),
                "rounds": [x["round"] for x in recs],
                "fathers": [x["father"] for x in recs],
                "before": [x["before"] for x in recs],
                "after": [x["after"] for x in recs],
                "benchmarks": sorted({x["benchmark"] for x in recs}),
            })
    dups = {
        "duplicate_string_groups": len(dup_groups),
        "duplicate_extra_occurrences": extra_occ,
        "same_parent_repeats": same_parent,
        "cross_parent_repeats": cross_parent,
        "cross_run_repeats": cross_run,
        "note": "AFlow check_modification is per-father local; cross-parent repeats may be by design",
        "groups": dup_groups[:30],
    }

    # ---- C2/C3: diversity via SHA-256 ----
    sha_groups = defaultdict(list)
    for r in rows:
        sha_groups[r["graph_sha"]].append(r["round"])
    diversity = {
        "raw_text_sha256_unique": len(sha_groups),
        "n_records": len(rows),
        "raw_text_diversity_ratio": len(sha_groups) / len(rows) if rows else 0,
        "duplicate_graph_shas": {k: v for k, v in sha_groups.items() if len(v) > 1},
        "normalized_ast_diversity": "NOT_COMPUTED (requires AST parse of graph.py)",
        "operator_composition_diversity": "NOT_COMPUTED",
        "lineage_diversity": "see lineage_metrics",
        "behavioral_diversity": "NOT_AVAILABLE (no comparable exec traces mined)",
    }

    # ---- D: parent selection concentration per (bench, variant) ----
    lineage = {}
    for bench in sorted({r["benchmark"] for r in rows}):
        for var in sorted({r["variant"] for r in rows if r["benchmark"] == bench}):
            sub = [r for r in rows if r["benchmark"] == bench and r["variant"] == var]
            fathers = Counter(str(r["father"]) for r in sub)
            total = sum(fathers.values())
            if total == 0:
                continue
            freqs = [c / total for c in fathers.values()]
            entropy = -sum(p * __import__("math").log(p) for p in freqs if p > 0)
            eff = 2 ** entropy
            lineage[f"{bench}/{var}"] = {
                "n_children": total,
                "parent_selection_frequency": dict(fathers),
                "selection_entropy_bits": entropy,
                "effective_parent_count": eff,
                "max_father_share": max(freqs),
                "plateau_note": "see best-score curve in prior stage; causality NOT established",
            }

    (OUT / "corrected_statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    (OUT / "discrepancy_cases.json").write_text(json.dumps({
        "n_discrepancies": len(discrep),
        "cause_counts": dict(causes),
        "cases": discrep,
    }, indent=2), encoding="utf-8")
    (OUT / "inheritance_metrics.json").write_text(json.dumps(inherit, indent=2), encoding="utf-8")
    (OUT / "duplicate_groups.json").write_text(json.dumps(dups, indent=2), encoding="utf-8")
    (OUT / "lineage_metrics.json").write_text(json.dumps(lineage, indent=2), encoding="utf-8")

    print("ALL", json.dumps(stats["ALL"], indent=2))
    print("discrepancies", len(discrep), dict(causes))
    print("inherit", json.dumps(inherit, indent=2))
    print("dups groups=%d extra=%d same_parent=%d cross_parent=%d" % (
        dups["duplicate_string_groups"], dups["duplicate_extra_occurrences"],
        dups["same_parent_repeats"], dups["cross_parent_repeats"]))
    print("GSM8K/graphs lineage", json.dumps(lineage.get("GSM8K/graphs"), indent=2))


if __name__ == "__main__":
    main()
