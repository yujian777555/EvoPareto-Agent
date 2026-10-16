"""Stage 1 result analysis: gates, genome comparison, pareto signal.

Reads real episode artifacts + DecisionLogs. No API calls.
"""
from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage1_feasibility"
EPDIR = OUT / "episodes"


def load_episodes() -> List[Dict[str, Any]]:
    rows = []
    for p in sorted(EPDIR.glob("*.json")):
        rows.append(json.loads(p.read_text(encoding="utf-8")))
    return rows


def main() -> None:
    eps = load_episodes()
    # Prefer completed episodes with won field
    completed = [e for e in eps if "won" in e or "success" in e]
    summary_path = OUT / "raw_episode_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}

    # normalize
    for e in completed:
        if "won" not in e and "success" in e:
            e["won"] = bool(e["success"])

    n = len(completed)
    wins = [e for e in completed if e.get("won")]
    n_win = len(wins)

    # ---- per genome ----
    by_g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for e in completed:
        by_g[e.get("genome_id") or e.get("episode_id", "").split("_")[1]].append(e)

    def agg(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {}
        wins = sum(1 for r in rows if r.get("won"))
        costs = [float(r.get("cost_usd") or 0) for r in rows]
        steps = [int(r.get("steps") or 0) for r in rows]
        tins = [int(r.get("tokens_in") or 0) for r in rows]
        tous = [int(r.get("tokens_out") or 0) for r in rows]
        http = [int(r.get("llm_call_count") or 0) for r in rows]
        refl = [int(r.get("reflection_count") or 0) for r in rows]
        # fallback / parse from decision logs if present
        n_fb = n_parse_fail = n_dl = 0
        for r in rows:
            for d in r.get("decision_logs") or []:
                n_dl += 1
                if d.get("used_fallback"):
                    n_fb += 1
                if not d.get("parse_ok", True):
                    n_parse_fail += 1
        return {
            "n_episodes": len(rows),
            "won_count": wins,
            "won_rate": wins / len(rows),
            "mean_cost_usd": sum(costs) / len(costs),
            "mean_steps": sum(steps) / len(steps),
            "mean_tokens_in": sum(tins) / len(tins),
            "mean_tokens_out": sum(tous) / len(tous),
            "mean_llm_calls": sum(http) / len(http),
            "mean_reflection_count": sum(refl) / len(refl),
            "fallback_count": n_fb,
            "parse_failure_count": n_parse_fail,
            "decision_log_count": n_dl,
        }

    genome_comparison = {
        "G1": agg(by_g.get("G1", [])),
        "G2": agg(by_g.get("G2", [])),
        "G3": agg(by_g.get("G3", [])),
        "overall": agg(completed),
    }
    (OUT / "genome_comparison.json").write_text(
        json.dumps(genome_comparison, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- paired (task_index, seed) blocks ----
    paired: Dict[tuple, Dict[str, Any]] = defaultdict(dict)
    for e in completed:
        key = (e.get("task_index"), e.get("seed"))
        gid = e.get("genome_id")
        paired[key][gid] = {
            "won": bool(e.get("won")),
            "cost_usd": float(e.get("cost_usd") or 0),
            "steps": int(e.get("steps") or 0),
            "tokens_in": int(e.get("tokens_in") or 0),
            "tokens_out": int(e.get("tokens_out") or 0),
            "llm_call_count": int(e.get("llm_call_count") or 0),
            "reflection_count": int(e.get("reflection_count") or 0),
        }

    paired_rows = []
    won_diff_blocks = 0
    cost_only_blocks = 0
    for (t, s), gm in sorted(paired.items(), key=lambda x: (x[0][0] or 0, x[0][1] or 0)):
        wons = {g: v["won"] for g, v in gm.items()}
        distinct_won = len(set(wons.values())) > 1
        if distinct_won:
            won_diff_blocks += 1
        costs = [v["cost_usd"] for v in gm.values()]
        cost_differs = (max(costs) - min(costs)) > 1e-9 if costs else False
        if cost_differs and not distinct_won:
            cost_only_blocks += 1
        paired_rows.append(
            {
                "task_index": t,
                "seed": s,
                "won_by_genome": wons,
                "won_differs_across_genomes": distinct_won,
                "cost_differs": cost_differs,
                "classification": (
                    "won_difference" if distinct_won
                    else ("cost_only_difference" if cost_differs else "identical_outcomes")
                ),
                "detail": gm,
            }
        )

    paired_task_results = {
        "n_paired_blocks": len(paired_rows),
        "won_difference_blocks": won_diff_blocks,
        "cost_only_difference_blocks": cost_only_blocks,
        "blocks": paired_rows,
        "gate2_screen": {
            "criterion": ">=2 paired blocks with differing won across genomes",
            "won_difference_blocks": won_diff_blocks,
            "result": "PASS" if won_diff_blocks >= 2 else (
                "COST_DISTINGUISHABILITY_ONLY" if cost_only_blocks >= 1 else "INCONCLUSIVE"
            ),
        },
    }
    (OUT / "paired_task_results.json").write_text(
        json.dumps(paired_task_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- decision log summary ----
    total_decisions = 0
    parse_fails = 0
    fallbacks = 0
    reflections = 0
    tokens_in = tokens_out = 0
    cost = 0.0
    action_counter: Counter = Counter()
    for e in completed:
        for d in e.get("decision_logs") or []:
            total_decisions += 1
            if not d.get("parse_ok", True):
                parse_fails += 1
            if d.get("used_fallback"):
                fallbacks += 1
            if d.get("reflection_trigger"):
                reflections += 1
            tokens_in += int(d.get("tokens_in") or 0)
            tokens_out += int(d.get("tokens_out") or 0)
            cost += float(d.get("estimated_cost_usd") or 0)
            action_counter[d.get("executed_action") or d.get("parsed_action") or ""] += 1

    # loop metric on all steps
    all_steps = sum(int(e.get("steps") or 0) for e in completed)
    decision_log_summary = {
        "total_decisions": total_decisions,
        "parse_failures": parse_fails,
        "fallbacks": fallbacks,
        "reflections": reflections,
        "fallback_rate": fallbacks / total_decisions if total_decisions else 0,
        "parse_failure_rate": parse_fails / total_decisions if total_decisions else 0,
        "reflection_rate": reflections / total_decisions if total_decisions else 0,
        "decision_tokens_in": tokens_in,
        "decision_tokens_out": tokens_out,
        "decision_cost_usd": cost,
        "top_actions": action_counter.most_common(20),
        "total_env_steps": all_steps,
        "raw_llm_available": total_decisions > 0,
    }
    (OUT / "decision_log_summary.json").write_text(
        json.dumps(decision_log_summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- pareto signal ----
    # genome-level aggregates as points (performance, cost)
    points = []
    for gid in ("G1", "G2", "G3"):
        g = genome_comparison.get(gid) or {}
        if g:
            points.append(
                {
                    "genome_id": gid,
                    "performance": g["won_rate"],
                    "cost_usd": g["mean_cost_usd"],
                    "n": g["n_episodes"],
                }
            )
    # non-dominated check: maximize performance, minimize cost
    def dominates(a, b):
        return (
            a["performance"] >= b["performance"]
            and a["cost_usd"] <= b["cost_usd"]
            and (a["performance"] > b["performance"] or a["cost_usd"] < b["cost_usd"])
        )

    nd = [p for p in points if not any(dominates(q, p) for q in points if q is not p)]
    all_zero_perf = all(p["performance"] == 0 for p in points)

    pareto_signal = {
        "genome_aggregate_points": points,
        "non_dominated_count": len(nd),
        "non_dominated": nd,
        "all_performance_zero": all_zero_perf,
        "signal": (
            "DEGENERATE" if all_zero_perf else
            ("INCONCLUSIVE" if sum(1 for p in points if p["performance"] > 0) < 2 else "CANDIDATE")
        ),
        "note": "cheaper failure is NOT better performance; performance=0 for all cells",
    }
    (OUT / "pareto_signal.json").write_text(
        json.dumps(pareto_signal, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- gates ----
    gate1 = "PASS" if n_win >= 1 else "FAIL"
    gate2 = paired_task_results["gate2_screen"]["result"]
    gate3 = pareto_signal["signal"]
    gates = {
        "GATE1_SOLVABILITY": {
            "result": gate1,
            "won_count": n_win,
            "episodes": n,
            "detail": "native won=true count among 18 episodes",
        },
        "GATE2_GENOME_DISTINGUISHABILITY": {
            "result": gate2,
            "won_difference_blocks": won_diff_blocks,
            "cost_only_blocks": cost_only_blocks,
            "criterion": ">=2 paired blocks with differing won (descriptive screen)",
        },
        "GATE3_MULTIOBJECTIVE_SIGNAL": {
            "result": gate3,
            "all_performance_zero": all_zero_perf,
            "non_dominated_count": len(nd),
        },
        "FINAL_DECISION": (
            "STOP / SOLVABILITY_DIAGNOSIS" if gate1 == "FAIL"
            else (
                "REVIEW / NO AUTOMATIC EXPANSION"
                if gate2 in ("INCONCLUSIVE", "COST_DISTINGUISHABILITY_ONLY")
                or gate3 in ("INCONCLUSIVE", "DEGENERATE")
                else "REQUEST STAGE 2 APPROVAL"
            )
        ),
    }
    (OUT / "gate_decisions.json").write_text(
        json.dumps(gates, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ---- ledger snapshot ----
    ledger = {}
    db_path = OUT / "budget.sqlite"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        r = conn.execute("SELECT * FROM budget WHERE id=1").fetchone()
        ledger = dict(r) if r else {}
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT * FROM meta")}
        ledger["meta"] = meta
        ledger["ticket_status_counts"] = {
            row["status"]: row["c"]
            for row in conn.execute("SELECT status, COUNT(*) c FROM tickets GROUP BY status")
        }
        conn.close()

    # ---- audit report ----
    audit = {
        "stage": "STAGE1_FEASIBILITY",
        "status": "COMPLETED",
        "executed_episodes": n,
        "successful_episodes": n_win,
        "stopped_reason": summary.get("stopped_reason", "matrix_completed"),
        "exec_git_sha": summary.get("exec_git_sha") or (eps[0].get("exec_git_sha") if eps else ""),
        "manifest_sha256": summary.get("manifest_sha256") or (eps[0].get("manifest_sha256") if eps else ""),
        "ledger": ledger,
        "total_http": ledger.get("physical_attempts"),
        "total_tokens_in": ledger.get("tokens_in"),
        "total_tokens_out": ledger.get("tokens_out"),
        "total_cost_usd": ledger.get("spent_cost"),
        "billing_blocked": bool(ledger.get("meta", {}).get("billing_blocked")),
        "auto_retries": ledger.get("retries"),
        "gates": gates,
        "interpretation_limit": "Stage 1 feasibility only — not PEEM/PPEC evidence",
    }
    (OUT / "audit_report.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("episodes", n, "wins", n_win)
    print("GATE1", gate1, "GATE2", gate2, "GATE3", gate3)
    print("FINAL", gates["FINAL_DECISION"])
    print("http", ledger.get("physical_attempts"), "cost", ledger.get("spent_cost"))
    print("WROTE analysis jsons")


if __name__ == "__main__":
    main()
