"""Analyze real AFlow official evolution results (no API).

Research questions:
  A. Do successful modifications get inherited/reused?
  B. Does parent selection collapse diversity?
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "external" / "AFlow_results" / "results"
OUT = ROOT / "results" / "stage3_0_p1_r2"
OUT.mkdir(parents=True, exist_ok=True)


def load_bench(bench_dir: Path):
    """Return rounds: [{round, score, father, modification, succeed, after, before, graph, prompt}]."""
    rounds = []
    for rd in sorted(bench_dir.glob("round_*"), key=lambda p: int(p.name.split("_")[1])):
        n = int(rd.name.split("_")[1])
        exp = {}
        ep = rd / "experience.json"
        if ep.exists() and ep.stat().st_size > 0:
            try:
                exp = json.loads(ep.read_text(encoding="utf-8"))
            except Exception:
                exp = {}
        graph = (rd / "graph.py").read_text(encoding="utf-8") if (rd / "graph.py").exists() else ""
        prompt = (rd / "prompt.py").read_text(encoding="utf-8") if (rd / "prompt.py").exists() else ""
        # score from results.json by round, else from csv names
        rounds.append({
            "round": n,
            "father": exp.get("father node"),
            "modification": exp.get("modification"),
            "before": exp.get("before"),
            "after": exp.get("after"),
            "succeed": exp.get("succeed"),
            "graph": graph,
            "prompt": prompt,
            "graph_len": len(graph),
            "prompt_len": len(prompt),
        })
    # attach scores from results.json
    rj = bench_dir / "results.json"
    scores_by_round = defaultdict(list)
    if rj.exists() and rj.stat().st_size > 0:
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
            for row in data:
                if isinstance(row, dict) and "round" in row:
                    scores_by_round[row["round"]].append(float(row.get("score") or 0))
        except Exception:
            pass
    for r in rounds:
        sc = scores_by_round.get(r["round"]) or ([r["after"]] if r["after"] is not None else [])
        r["scores"] = sc
        r["mean_score"] = sum(sc) / len(sc) if sc else None
    return rounds


def analyze_bench(name: str, rounds):
    n = len(rounds)
    succeeds = [r for r in rounds if r["succeed"] is True]
    fails = [r for r in rounds if r["succeed"] is False]
    fathers = Counter(r["father"] for r in rounds)
    mods = [r["modification"] for r in rounds if r["modification"]]
    dup_mods = [m for m, c in Counter(mods).items() if c > 1]

    # inheritance: a successful mod's father gets more children later?
    succ_fathers = {r["father"] for r in succeeds}
    children_of_succ = sum(1 for r in rounds if r["father"] in succ_fathers)
    # best-so-far score curve
    best, curve = -1.0, []
    for r in sorted(rounds, key=lambda x: x["round"]):
        for s in r["scores"]:
            best = max(best, s)
        curve.append(best if best >= 0 else None)
    # do low-score fathers produce better children?
    upgrades, downgrades, ties = 0, 0, 0
    for r in rounds:
        if r["before"] is not None and r["after"] is not None:
            d = r["after"] - r["before"]
            if d > 1e-9:
                upgrades += 1
            elif d < -1e-9:
                downgrades += 1
            else:
                ties += 1
    # structural diversity: unique graph hashes
    ghash = [hash(r["graph"]) for r in rounds]
    unique_graphs = len(set(ghash))
    # lineage depth
    depth_map = {}
    for r in sorted(rounds, key=lambda x: x["round"]):
        f = r["father"]
        depth_map[r["round"]] = depth_map.get(f, 0) + 1
    return {
        "benchmark": name,
        "n_rounds": n,
        "n_success": len(succeeds),
        "n_fail": len(fails),
        "success_rate": len(succeeds) / n if n else 0.0,
        "duplicate_modifications": dup_mods,
        "father_child_counts": dict(fathers),
        "children_of_successful_fathers": children_of_succ,
        "best_score_curve": curve,
        "final_best_score": max((s for r in rounds for s in r["scores"]), default=None),
        "upgrades": upgrades, "downgrades": downgrades, "ties": ties,
        "unique_graphs": unique_graphs,
        "graph_diversity_ratio": unique_graphs / n if n else 0.0,
        "lineage_depths": depth_map,
    }


def main():
    inventory = {}
    analyses = {}
    for bench in sorted(BASE.iterdir()):
        if not bench.is_dir():
            continue
        # each bench has run variants: graphs, ablation_graphs, graphs_test
        variant_summaries = {}
        for var in sorted(bench.iterdir()):
            if not var.is_dir():
                continue
            rounds = load_bench(var)
            if not rounds:
                continue
            variant_summaries[var.name] = analyze_bench(f"{bench.name}/{var.name}", rounds)
            inventory[f"{bench.name}/{var.name}"] = {
                "n_round_dirs": len(rounds),
                "has_experience": sum(1 for r in rounds if r["modification"]),
                "has_results": (var / "results.json").exists() and (var / "results.json").stat().st_size > 0,
                "has_logs": sum(1 for r in rounds if (var / f"round_{r['round']}" / "log.json").exists()),
            }
        analyses[bench.name] = variant_summaries

    (OUT / "historical_artifact_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    (OUT / "trace_analysis.json").write_text(json.dumps(analyses, indent=2), encoding="utf-8")

    # Research Q&A over all variants
    all_analyses = [a for variants in analyses.values() for a in variants.values()]
    total_succ = sum(a["n_success"] for a in all_analyses)
    total_rounds = sum(a["n_rounds"] for a in all_analyses)
    ups = sum(a["upgrades"] for a in all_analyses)
    downs = sum(a["downgrades"] for a in all_analyses)
    diversity = {a["benchmark"]: a["graph_diversity_ratio"] for a in all_analyses}
    dup_total = sum(len(a["duplicate_modifications"]) for a in all_analyses)

    qa = {
        "Q_A_success_inheritance": {
            "total_success_mods": total_succ,
            "total_mods": total_rounds,
            "success_rate": total_succ / total_rounds if total_rounds else 0,
            "duplicate_mod_count": dup_total,
            "exact_string_dedup_impact": (
                "AFlow blacklists exact modification strings (success AND failure). "
                "Duplicate mods found in official data: %d — dedup is weak/lenient or "
                "runs are independent." % dup_total
            ),
            "per_variant_success": {a["benchmark"]: a["n_success"] for a in all_analyses},
        },
        "Q_B_diversity_collapse": {
            "graph_diversity_ratio": diversity,
            "father_child_counts": {a["benchmark"]: a["father_child_counts"] for a in all_analyses},
            "upgrade_vs_downgrade": {"upgrades": ups, "downgrades": downs},
            "best_score_curves": {a["benchmark"]: a["best_score_curve"] for a in all_analyses},
            "interpretation": (
                "Parent distribution and unique-graph ratio quantify diversity; "
                "upgrades/downgrades show whether low-score parents can yield better children."
            ),
        },
        "limitations": [
            "CSV per-sample scores not yet parsed (filenames encode scores)",
            "correlation != causation; no counterfactual re-run",
            "log.json execution traces not yet mined",
        ],
        "evidence_class": "OFFICIAL_HISTORICAL_ARTIFACT",
    }
    (OUT / "research_questions_analysis.json").write_text(json.dumps(qa, indent=2), encoding="utf-8")

    print(json.dumps({
        "variants": list(inventory.keys())[:20],
        "total_rounds": total_rounds,
        "total_success": total_succ,
        "diversity": diversity,
        "upgrades": ups, "downgrades": downs,
    }, indent=2))


if __name__ == "__main__":
    main()
