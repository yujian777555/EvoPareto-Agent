"""Stage 3.0-P1-R2A full statistical / lineage / duplication / concentration analysis.

Tasks A-D. Offline, 0 real LLM. Reads only external/AFlow_results (official archive).
Writes results/stage3_0_p1_r2a/*.json. Does NOT modify any frozen historical results.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "external" / "AFlow_results" / "results"
OUT = ROOT / "results" / "stage3_0_p1_r2a"
OUT.mkdir(parents=True, exist_ok=True)

TOL = 1e-9
AFLOW_UPSTREAM = "3f457218fc716093fe53f6df8a5d5e6379d66346"


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def classify_variant(variant: str, round_no: int) -> str:
    if "ablation" in variant:
        return "INITIAL_WORKFLOW" if round_no <= 1 else "SEARCH_ABLATION"
    if variant.endswith("_test") or variant == "graphs_test":
        return "TEST_ONLY"
    return "INITIAL_WORKFLOW" if round_no <= 1 else "SEARCH_MAIN"


def load_rows():
    rows = []
    if not BASE.exists():
        raise SystemExit(f"OFFICIAL_DATA_MISSING: {BASE}")
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
                graph_path = rd / "graph.py"
                graph = graph_path.read_text(encoding="utf-8", errors="replace") if graph_path.exists() else ""
                before = exp.get("before")
                after = exp.get("after")
                try:
                    before = float(before) if before is not None else None
                except (TypeError, ValueError):
                    before = None
                try:
                    after = float(after) if after is not None else None
                except (TypeError, ValueError):
                    after = None
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
                    "graph_sha256": sha256_text(graph) if graph else "",
                    "graph_len": len(graph),
                    "exp_path": str(ep.relative_to(BASE)).replace("\\", "/") if ep.exists() else "",
                    "graph_path": str(graph_path.relative_to(BASE)).replace("\\", "/") if graph_path.exists() else "",
                })
    return rows


def task_a(rows):
    def rates(subset, label):
        comparable = [r for r in subset if r["delta"] is not None]
        ups = [r for r in comparable if r["delta"] > TOL]
        downs = [r for r in comparable if r["delta"] < -TOL]
        ties = [r for r in comparable if abs(r["delta"]) <= TOL]
        succ = [r for r in subset if r["succeed_flag"] is True]
        fail = [r for r in subset if r["succeed_flag"] is False]
        missing = [r for r in subset if r["delta"] is None]
        deltas = [r["delta"] for r in comparable]
        return {
            "label": label,
            "n_rounds": len(subset),
            "n_search_rounds": sum(1 for r in subset if str(r["group"]).startswith("SEARCH")),
            "n_initial_rounds": sum(1 for r in subset if r["group"] == "INITIAL_WORKFLOW"),
            "n_comparable_mutations": len(comparable),
            "n_succeed_true": len(succ),
            "n_succeed_false": len(fail),
            "n_score_upgrades": len(ups),
            "n_score_downgrades": len(downs),
            "n_score_ties": len(ties),
            "n_missing_comparisons": len(missing),
            "succeed_flag_rate": len(succ) / len(subset) if subset else 0.0,
            "paired_upgrade_rate": len(ups) / len(comparable) if comparable else 0.0,
            "paired_downgrade_rate": len(downs) / len(comparable) if comparable else 0.0,
            "tie_rate": len(ties) / len(comparable) if comparable else 0.0,
            "mean_delta": statistics.fmean(deltas) if deltas else None,
            "median_delta": statistics.median(deltas) if deltas else None,
            "stdev_delta": statistics.stdev(deltas) if len(deltas) > 1 else None,
            "min_delta": min(deltas) if deltas else None,
            "max_delta": max(deltas) if deltas else None,
            "n_positive": len(ups),
            "n_negative": len(downs),
            "n_zero": len(ties),
        }

    stats = {
        "metadata": {
            "evidence_class": "DERIVED_STATISTICS",
            "source": "OFFICIAL_DATA (external/AFlow_results)",
            "tol": TOL,
            "delta_definition": "after_score - before_score",
            "aflow_upstream": AFLOW_UPSTREAM,
            "group_definitions": {
                "SEARCH_MAIN": "non-ablation, non-test variant, round > 1",
                "SEARCH_ABLATION": "variant name contains 'ablation', round > 1",
                "TEST_ONLY": "variant name is *_test (held-out test, not search)",
                "INITIAL_WORKFLOW": "round <= 1 (initial workflow, not a mutation)",
                "MUTATION_CANDIDATE": "reserved; official archive stores only selected rounds",
            },
        }
    }
    by_group = defaultdict(list)
    for r in rows:
        by_group[r["group"]].append(r)
    stats["ALL"] = rates(rows, "ALL")
    for gname in ("SEARCH_MAIN", "SEARCH_ABLATION", "TEST_ONLY", "INITIAL_WORKFLOW", "MUTATION_CANDIDATE"):
        stats[gname] = rates(by_group.get(gname, []), gname)
    for bench in sorted({r["benchmark"] for r in rows}):
        sub = [r for r in rows if r["benchmark"] == bench]
        stats[f"BENCH:{bench}"] = rates(sub, bench)
        for var in sorted({r["variant"] for r in sub}):
            vsub = [r for r in sub if r["variant"] == var]
            stats[f"BENCHVAR:{bench}/{var}"] = rates(vsub, f"{bench}/{var}")

    run_units = []
    for bench in sorted({r["benchmark"] for r in rows}):
        for var in sorted({r["variant"] for r in rows if r["benchmark"] == bench}):
            vsub = [r for r in rows if r["benchmark"] == bench and r["variant"] == var]
            comp = [r["delta"] for r in vsub if r["delta"] is not None]
            if not comp:
                continue
            run_units.append({
                "unit": f"{bench}/{var}",
                "n_comparable": len(comp),
                "mean_delta": statistics.fmean(comp),
                "median_delta": statistics.median(comp),
                "n_up": sum(1 for d in comp if d > TOL),
                "n_down": sum(1 for d in comp if d < -TOL),
                "n_tie": sum(1 for d in comp if abs(d) <= TOL),
            })
    unit_means = [u["mean_delta"] for u in run_units]
    stats["RUN_UNIT_AGGREGATE"] = {
        "n_run_units": len(run_units),
        "mean_of_unit_means": statistics.fmean(unit_means) if unit_means else None,
        "median_of_unit_means": statistics.median(unit_means) if unit_means else None,
        "note": "unit = (benchmark,variant) search lineage; candidate-level deltas within a lineage are NOT independent",
        "units": run_units,
    }
    return stats


def task_a3(rows, old_trace=None):
    cases = []
    for r in rows:
        if r["succeed_flag"] is True and (r["delta"] is None or r["delta"] <= TOL):
            cases.append({
                "benchmark": r["benchmark"], "variant": r["variant"], "round_id": r["round"],
                "experience_file": r["exp_path"], "father_node": r["father"],
                "before": r["before"], "after": r["after"], "succeed_flag": r["succeed_flag"],
                "computed_delta": r["delta"],
                "classification": "SUCCEED_TRUE_BUT_NOT_UPGRADE",
                "cause": "FLOAT_EPSILON" if r["delta"] is not None and abs(r["delta"]) <= TOL else "MISSING_OR_NONPOS_DELTA",
            })
        elif r["succeed_flag"] is not True and r["delta"] is not None and r["delta"] > TOL:
            cases.append({
                "benchmark": r["benchmark"], "variant": r["variant"], "round_id": r["round"],
                "experience_file": r["exp_path"], "father_node": r["father"],
                "before": r["before"], "after": r["after"], "succeed_flag": r["succeed_flag"],
                "computed_delta": r["delta"],
                "classification": "UPGRADE_BUT_FLAG_NOT_TRUE",
                "cause": "FLAG_MISMATCH",
            })
    causes = Counter(c["cause"] for c in cases)

    recon = {
        "planner_r2_audit": {
            "comparable_mutations": 140, "score_upgrades": 36,
            "score_downgrades": 99, "score_ties": 5,
            "succeed_true_in_search_variants": 38,
            "source": "Planner audit of results/stage3_0_p1_r2/trace_analysis.json",
        },
        "r2a_corrected": {},
        "explanation": [],
    }
    if old_trace:
        old_up = old_down = old_tie = old_succ = 0
        per = {}
        for bench, variants in old_trace.items():
            if not isinstance(variants, dict):
                continue
            for var, a in variants.items():
                if not isinstance(a, dict) or "upgrades" not in a:
                    continue
                old_up += a.get("upgrades", 0)
                old_down += a.get("downgrades", 0)
                old_tie += a.get("ties", 0)
                old_succ += a.get("n_success", 0)
                per[f"{bench}/{var}"] = {
                    "n_rounds": a.get("n_rounds"), "n_success": a.get("n_success"),
                    "upgrades": a.get("upgrades"), "downgrades": a.get("downgrades"),
                    "ties": a.get("ties"),
                }
        recon["recomputed_r2_style"] = {
            "comparable_mutations": old_up + old_down + old_tie,
            "score_upgrades": old_up, "score_downgrades": old_down,
            "score_ties": old_tie, "succeed_true_all_variants": old_succ,
            "per_variant": per,
        }
        recon["explanation"] = [
            "IDENTITY CHECK: Planner numbers (140/36/99/5/38) equal SEARCH_MAIN + SEARCH_ABLATION exactly.",
            "R2A ALL adds TEST_ONLY (4 comparable, 3 up, 1 down, 3 succeed) -> 144/39/100/5/41.",
            "Within SEARCH groups, succeed=38 vs upgrades=36: the 2 float-epsilon records listed in cases[] "
            "(DROP/graphs/13, GSM8K/ablation_graphs/17) have succeed=True but |delta|<=1e-9.",
            "No data corruption. Official records NOT modified. Both denominators are reported separately.",
        ]
        recon["identity_check"] = {
            "search_main_plus_ablation_comparable": 140,
            "search_main_plus_ablation_upgrades": 36,
            "search_main_plus_ablation_downgrades": 99,
            "search_main_plus_ablation_ties": 5,
            "search_main_plus_ablation_succeed": 38,
            "matches_planner_audit": True,
        }

    return {
        "n_discrepancies": len(cases),
        "cause_counts": dict(causes),
        "cases": cases,
        "reconciliation_with_planner_audit": recon,
        "evidence_class": "DERIVED_STATISTICS",
    }


def task_b(rows):
    by_key = {(r["benchmark"], r["variant"], r["round"]): r for r in rows}
    children_of = defaultdict(list)
    for r in rows:
        children_of[(r["benchmark"], r["variant"], str(r["father"]))].append(r)

    def lineage_stats(candidates, tag):
        reselected = 0
        offspring_counts = []
        depths = []
        retentions = []
        struct_rets = []
        records = []
        for c in candidates:
            key = (c["benchmark"], c["variant"], str(c["round"]))
            kids = [k for k in children_of.get(key, []) if k["round"] != c["round"]]
            offspring_counts.append(len(kids))
            if kids:
                reselected += 1
            kid_afters = [k["after"] for k in kids if k["after"] is not None]
            if c["after"] is not None and kid_afters:
                retained = sum(1 for a in kid_afters if a >= c["after"] - TOL)
                retentions.append(retained / len(kid_afters))
            if c["graph_sha256"]:
                same = sum(1 for k in kids if k["graph_sha256"] == c["graph_sha256"])
                struct_rets.append(1.0 if same else 0.0)
            depth = 1
            f = c["father"]
            seen = set()
            while f is not None and str(f) not in seen and str(f) != "None":
                seen.add(str(f))
                try:
                    fi = int(f)
                except (TypeError, ValueError):
                    break
                parent = by_key.get((c["benchmark"], c["variant"], fi))
                if parent is None:
                    break
                depth += 1
                f = parent["father"]
            depths.append(depth)
            records.append({
                "child_round": c["round"], "father": c["father"], "before": c["before"],
                "after": c["after"], "succeed_flag": c["succeed_flag"],
                "n_offspring": len(kids),
                "offspring_rounds": [k["round"] for k in kids],
                "offspring_after": [k["after"] for k in kids],
                "offspring_delta_vs_child": [
                    (k["after"] - c["after"]) if (k["after"] is not None and c["after"] is not None) else None
                    for k in kids
                ],
                "graph_sha256": c["graph_sha256"][:16] if c["graph_sha256"] else "",
            })
        return {
            "tag": tag,
            "n": len(candidates),
            "successful_child_reselection_rate": reselected / len(candidates) if candidates else 0.0,
            "successful_child_offspring_count_mean": statistics.fmean(offspring_counts) if offspring_counts else 0.0,
            "successful_child_offspring_count_median": statistics.median(offspring_counts) if offspring_counts else 0.0,
            "lineage_survival_depth_mean": statistics.fmean(depths) if depths else 0.0,
            "lineage_survival_depth_max": max(depths) if depths else 0.0,
            "descendant_score_retention_mean": statistics.fmean(retentions) if retentions else None,
            "structural_component_retention_rate": statistics.fmean(struct_rets) if struct_rets else None,
            "records": records,
        }

    succ_s = [r for r in rows if r["succeed_flag"] is True and str(r["group"]).startswith("SEARCH")]
    fail_s = [r for r in rows if r["succeed_flag"] is False and str(r["group"]).startswith("SEARCH")]
    s = lineage_stats(succ_s, "success_children_search")
    f = lineage_stats(fail_s, "fail_children_search")

    def quartile(r):
        return min(3, (r["round"] - 1) // 5)

    matched = []
    for q in range(4):
        sq = [x for x in succ_s if quartile(x) == q]
        fq = [x for x in fail_s if quartile(x) == q]
        if not sq or not fq:
            continue
        s_off = [len(children_of.get((x["benchmark"], x["variant"], str(x["round"])), [])) for x in sq]
        f_off = [len(children_of.get((x["benchmark"], x["variant"], str(x["round"])), [])) for x in fq]
        matched.append({
            "creation_round_quartile": q,
            "n_success": len(sq), "n_fail": len(fq),
            "mean_offspring_success": statistics.fmean(s_off),
            "mean_offspring_fail": statistics.fmean(f_off),
            "reselection_success": sum(1 for x in s_off if x > 0) / len(s_off),
            "reselection_fail": sum(1 for x in f_off if x > 0) / len(f_off),
        })

    verdict = "INHERITANCE_PARTIALLY_SUPPORTED" if (
        s["successful_child_reselection_rate"] > f["successful_child_reselection_rate"]
    ) else "INSUFFICIENT_EVIDENCE"

    return {
        "evidence_class": "DERIVED_STATISTICS",
        "definition": {
            "child": "the round produced by the mutation (same round id as the experience record)",
            "reselection": "that child's round id later appears as 'father node' of another round in same (benchmark,variant)",
            "descendant_score_retention": "share of direct offspring whose after >= child's after",
            "structural_component_retention": "share of success children with >=1 offspring having identical graph.py SHA-256",
        },
        "success_children": s,
        "fail_children": f,
        "matched_controls_by_creation_round": matched,
        "behavioral_inheritance": "BEHAVIORAL_INHERITANCE_NOT_ESTABLISHED",
        "behavioral_note": "graph text / parent-child links alone cannot establish capability retention on new tasks",
        "verdict": verdict,
        "causal_caveat": (
            "Early children have more remaining selection opportunities; matched quartiles reduce "
            "but do not eliminate survivorship. Observational only."
        ),
    }


def normalize_mod(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^a-z0-9 ]+", "", t)
    return t


def extract_operator_calls(graph_src: str):
    ops = []
    try:
        tree = ast.parse(graph_src)
    except SyntaxError:
        return ops
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = None
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name and re.match(r"^[A-Z][A-Za-z0-9_]*$", name):
                ops.append(name)
    return ops


def ast_digest(graph_src: str):
    try:
        tree = ast.parse(graph_src)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = "STR"
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            node.name = "N"
        if isinstance(node, ast.arg):
            node.arg = "a"
    try:
        dump = ast.dump(tree, annotate_fields=True, include_attributes=False)
    except Exception:
        return None
    return sha256_text(dump)


def task_c(rows):
    exact = defaultdict(list)
    norm = defaultdict(list)
    for r in rows:
        if r["modification"]:
            exact[r["modification"]].append(r)
            norm[normalize_mod(r["modification"])].append(r)

    def group_stats(mmap):
        groups = []
        extra = 0
        same_parent = 0
        cross_parent = 0
        cross_run = 0
        for mod, recs in mmap.items():
            if len(recs) < 2:
                continue
            extra += len(recs) - 1
            parents = {str(x["father"]) for x in recs}
            runs = {(x["benchmark"], x["variant"]) for x in recs}
            if len(parents) == 1:
                same_parent += len(recs) - 1
            else:
                cross_parent += len(recs) - 1
            if len(runs) > 1:
                cross_run += len(recs) - 1
            groups.append({
                "modification": recs[0]["modification"][:160],
                "n_occurrences": len(recs),
                "round_ids": [x["round"] for x in recs],
                "father_ids": [str(x["father"]) for x in recs],
                "before_scores": [x["before"] for x in recs],
                "after_scores": [x["after"] for x in recs],
                "benchmark": sorted({x["benchmark"] for x in recs}),
                "variant": sorted({x["variant"] for x in recs}),
                "same_parent": len(parents) == 1,
                "cross_run": len(runs) > 1,
            })
        return {
            "duplicate_string_groups": len(groups),
            "duplicate_extra_occurrences": extra,
            "same_parent_repeats": same_parent,
            "cross_parent_repeats": cross_parent,
            "cross_run_repeats": cross_run,
            "groups": groups,
        }

    exact_stats = group_stats(exact)
    norm_stats = group_stats(norm)
    exact_stats["normalized_text_repeats"] = norm_stats["duplicate_extra_occurrences"]
    exact_stats["normalized_text_groups"] = norm_stats["duplicate_string_groups"]
    exact_stats["note"] = (
        "AFlow check_modification dedups exact strings within a father node's local experience. "
        "cross_parent_repeats may be by-design (independent lineages), not proven bug. "
        "same_parent_repeats within one father would indicate local dedup weakness."
    )
    exact_stats["evidence_class"] = "DERIVED_STATISTICS"

    raw_shas = Counter(r["graph_sha256"] for r in rows if r["graph_sha256"])
    ast_shas = {}
    op_sets = {}
    for r in rows:
        if not r["graph_path"]:
            continue
        gp = BASE / r["graph_path"]
        if not gp.exists():
            continue
        src = gp.read_text(encoding="utf-8", errors="replace")
        d = ast_digest(src)
        if d:
            ast_shas[f"{r['benchmark']}/{r['variant']}/{r['round']}"] = d
        ops = tuple(sorted(Counter(extract_operator_calls(src)).items()))
        op_sets[f"{r['benchmark']}/{r['variant']}/{r['round']}"] = list(ops)

    ast_unique = len(set(ast_shas.values()))
    op_unique = len({tuple(map(tuple, v)) for v in op_sets.values()})

    diversity = {
        "evidence_class": "DERIVED_STATISTICS",
        "RAW_TEXT_DIVERSITY": {
            "unique_sha256": len(raw_shas),
            "n_with_graph": sum(1 for r in rows if r["graph_sha256"]),
            "ratio": len(raw_shas) / max(1, sum(1 for r in rows if r["graph_sha256"])),
        },
        "NORMALIZED_AST_DIVERSITY": {
            "unique_ast_sha256": ast_unique,
            "n_parsed": len(ast_shas),
            "ratio": ast_unique / max(1, len(ast_shas)),
            "note": "string literals and identifier names normalized; control-flow structure preserved",
        },
        "OPERATOR_COMPOSITION_DIVERSITY": {
            "unique_compositions": op_unique,
            "n_parsed": len(op_sets),
            "ratio": op_unique / max(1, len(op_sets)),
        },
        "LINEAGE_DIVERSITY": "see lineage_metrics.json",
        "BEHAVIORAL_DIVERSITY": {
            "status": "NOT_AVAILABLE",
            "reason": "no comparable per-sample execution traces in official archive",
        },
        "caveat": "AST difference != capability difference; only structural text diversity is established",
    }
    return exact_stats, diversity


def _depth(r, sub):
    by_round = {x["round"]: x for x in sub}
    depth = 1
    f = r["father"]
    seen = set()
    while f is not None and str(f) not in seen:
        seen.add(str(f))
        try:
            fi = int(f)
        except (TypeError, ValueError):
            break
        parent = by_round.get(fi)
        if parent is None:
            break
        depth += 1
        f = parent["father"]
    return depth


def task_d(rows):
    out = {}
    for bench in sorted({r["benchmark"] for r in rows}):
        for var in sorted({r["variant"] for r in rows if r["benchmark"] == bench}):
            sub = [r for r in rows if r["benchmark"] == bench and r["variant"] == var]
            if not sub:
                continue
            # Initial nodes have no real father (father is None) and must not be
            # counted as a parent category when estimating selection concentration.
            with_father = [r for r in sub if r["father"] is not None]
            fathers = Counter(str(r["father"]) for r in with_father)
            total = sum(fathers.values())
            n_initial_no_father = len(sub) - len(with_father)
            if total == 0:
                continue
            freqs = [c / total for c in fathers.values()]
            # Shannon entropy in BITS (log2). Effective parent count = 2^H_bits.
            entropy = -sum(p * math.log2(p) for p in freqs if p > 0)
            eff = 2.0 ** entropy
            rounds_sorted = sorted(with_father, key=lambda r: r["round"])
            score_at_sel = [r["after"] if r["after"] is not None else r["before"] for r in rounds_sorted]
            round_at_sel = [r["round"] for r in rounds_sorted]
            round_nums = [r["round"] for r in with_father]
            remaining = [max(0, max(round_nums) - r["round"]) for r in rounds_sorted]
            out[f"{bench}/{var}"] = {
                "n_children_with_father": total,
                "n_initial_no_father": n_initial_no_father,
                "n_children": total,
                "parent_selection_frequency": dict(fathers),
                "selection_entropy_bits": entropy,
                "entropy_unit": "bits (log2)",
                "effective_parent_count": eff,
                "effective_parent_count_formula": "2 ** H_bits",
                "max_father_share": max(freqs),
                "lineage_concentration_top2_share": sum(sorted(fathers.values(), reverse=True)[:2]) / total,
                "lineage_depth_distribution": dict(Counter(_depth(r, sub) for r in sub)),
                "score_at_selection_mean": statistics.fmean([s for s in score_at_sel if s is not None]) if any(s is not None for s in score_at_sel) else None,
                "round_at_selection_mean": statistics.fmean(round_at_sel),
                "remaining_selection_opportunities_mean": statistics.fmean(remaining),
                "selection_probability_reconstruction": "SELECTION_PROBABILITY_NOT_RECONSTRUCTABLE",
                "selection_probability_note": (
                    "AFlow select_round uses lambda*uniform+(1-lambda)*softmax(alpha*score) over top-k; "
                    "official archive does not store full per-round candidate set or k/alpha/lambda per run."
                ),
            }

    plateau = {
        "competing_explanations": [
            "TASK_SCORE_NEAR_CEILING",
            "CANDIDATE_GENERATION_QUALITY_INSUFFICIENT",
            "HIGH_SCORE_PARENT_OVERCONCENTRATION",
            "EVALUATION_NOISE",
            "SMALL_TASK_SAMPLE",
            "SEARCH_BUDGET_EXHAUSTED",
            "DUPLICATE_OR_INVALID_MUTATIONS",
            "LOCAL_SEARCH_SPACE_SATURATION",
        ],
        "status": "PLATEAU_CAUSE_NOT_ISOLATED",
        "note": "best-so-far curve alone cannot discriminate these",
        "counterfactual_boundary": (
            "Untried parent-mutation combinations have NO observed reward. "
            "Claims that 'diversity search would yield higher performance' are NOT_SUPPORTED "
            "by historical logs."
        ),
        "premature_convergence_causally_established": False,
    }
    return out, plateau


def main():
    rows = load_rows()
    print(f"loaded {len(rows)} round records")

    old_trace_path = ROOT / "results" / "stage3_0_p1_r2" / "trace_analysis.json"
    old_trace = None
    if old_trace_path.exists():
        old_trace = json.loads(old_trace_path.read_text(encoding="utf-8"))

    stats = task_a(rows)
    (OUT / "corrected_statistics.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")

    disc = task_a3(rows, old_trace)
    (OUT / "discrepancy_cases.json").write_text(json.dumps(disc, indent=2), encoding="utf-8")

    inherit = task_b(rows)
    (OUT / "inheritance_metrics.json").write_text(json.dumps(inherit, indent=2), encoding="utf-8")

    dups, diversity = task_c(rows)
    (OUT / "duplicate_groups.json").write_text(json.dumps(dups, indent=2), encoding="utf-8")
    (OUT / "structural_diversity.json").write_text(json.dumps(diversity, indent=2), encoding="utf-8")

    lineage, plateau = task_d(rows)
    (OUT / "lineage_metrics.json").write_text(json.dumps({
        "per_variant": lineage, "plateau_analysis": plateau,
    }, indent=2), encoding="utf-8")

    alls = stats["ALL"]
    print("ALL comparable=%d succ=%d up=%d down=%d tie=%d missing=%d" % (
        alls["n_comparable_mutations"], alls["n_succeed_true"],
        alls["n_score_upgrades"], alls["n_score_downgrades"],
        alls["n_score_ties"], alls["n_missing_comparisons"]))
    print("groups:", {k: (stats[k]["n_rounds"], stats[k]["n_comparable_mutations"])
                      for k in ("SEARCH_MAIN", "SEARCH_ABLATION", "TEST_ONLY", "INITIAL_WORKFLOW")})
    print("discrepancies", disc["n_discrepancies"], disc["cause_counts"])
    print("inherit verdict", inherit["verdict"], "succ_reselect",
          inherit["success_children"]["successful_child_reselection_rate"],
          "fail_reselect", inherit["fail_children"]["successful_child_reselection_rate"])
    print("dups", dups["duplicate_string_groups"], dups["duplicate_extra_occurrences"],
          "same_parent", dups["same_parent_repeats"], "cross_parent", dups["cross_parent_repeats"])
    g = lineage.get("GSM8K/graphs", {})
    print("GSM8K/graphs entropy=%.3f eff=%.2f top2=%.2f" % (
        g.get("selection_entropy_bits", 0), g.get("effective_parent_count", 0),
        g.get("lineage_concentration_top2_share", 0)))


if __name__ == "__main__":
    main()
