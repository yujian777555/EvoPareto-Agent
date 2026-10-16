"""Stage 1.6 A/B result analysis."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage1_6"
EPDIR = OUT / "episodes"


def load():
    # prefer summary rows (have won/task_index); fall back to episode files
    summary_path = OUT / "raw_episode_summary.json"
    rows = []
    if summary_path.exists():
        raw = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = raw.get("episodes") or []
    if rows:
        return rows
    out = []
    for p in sorted(EPDIR.glob("*.json")):
        e = json.loads(p.read_text(encoding="utf-8"))
        e.setdefault("won", bool(e.get("success")))
        # recover task_index from episode_id like t0_current_r1
        if e.get("task_index") is None:
            m = re.match(r"t(\d+)_", p.name)
            if m:
                e["task_index"] = int(m.group(1))
        out.append(e)
    return out


def loop_metrics(ep):
    # summary rows lack trajectory — load from episode file if needed
    traj = ep.get("trajectory")
    if traj is None:
        eid = ep.get("episode_id")
        p = EPDIR / f"{eid}.json"
        if p.exists():
            traj = json.loads(p.read_text(encoding="utf-8")).get("trajectory") or []
        else:
            traj = []
    n = len(traj)
    if n == 0:
        return {"steps": ep.get("steps") or 0, "loop_occ": 0, "rep_ratio": 0.0, "unique_locs": 0}
    acts = [str(t.get("action") or "") for t in traj]
    pair_c = Counter((str(t.get("observation_before") or "").strip(), a) for a, t in zip(acts, traj))
    loop_occ = sum(c - 1 for c in pair_c.values() if c > 1)
    return {
        "steps": n,
        "loop_occ": loop_occ,
        "rep_ratio": 1.0 - len(set(acts)) / n,
        "unique_locs": len({str(t.get("observation_after") or "")[:40] for t in traj}),
    }


def main():
    eps = load()
    by_rt = defaultdict(list)
    for e in eps:
        by_rt[e.get("runtime_variant") or "current"].append(e)

    def agg(rows):
        if not rows:
            return {}
        costs = [float(r.get("cost_usd") or 0) for r in rows]
        tins = [int(r.get("tokens_in") or 0) for r in rows]
        tous = [int(r.get("tokens_out") or 0) for r in rows]
        steps = [int(r.get("steps") or 0) for r in rows]
        wins = sum(1 for r in rows if r.get("won"))
        loops = [loop_metrics(r) for r in rows]
        return {
            "n": len(rows),
            "won": wins,
            "mean_cost_usd": sum(costs) / len(costs),
            "median_cost_usd": sorted(costs)[len(costs) // 2],
            "mean_tokens_in": sum(tins) / len(tins),
            "mean_tokens_out": sum(tous) / len(tous),
            "mean_steps": sum(steps) / len(steps),
            "mean_llm_calls": sum(int(r.get("llm_call_count") or 0) for r in rows) / len(rows),
            "mean_loop_occurrences": sum(x["loop_occ"] for x in loops) / len(loops),
            "mean_repetition_ratio": sum(x["rep_ratio"] for x in loops) / len(loops),
            "cost_per_success": (sum(costs) / wins) if wins else None,
        }

    cur = agg(by_rt.get("current", []))
    rep = agg(by_rt.get("shared_repaired", []))

    # paired cells
    paired = []
    by_cell = defaultdict(dict)
    for e in eps:
        key = (e.get("task_index"), e.get("repeat_id"))
        by_cell[key][e.get("runtime_variant")] = e
    rep_only = cur_only = ties = 0
    for (t, r), gm in sorted(by_cell.items(), key=lambda x: (x[0][0] or 0, x[0][1] or 0)):
        c_ok = bool(gm.get("current", {}).get("won"))
        r_ok = bool(gm.get("shared_repaired", {}).get("won"))
        if r_ok and not c_ok:
            rep_only += 1
        elif c_ok and not r_ok:
            cur_only += 1
        else:
            ties += 1
        paired.append({"task_index": t, "repeat_id": r,
                       "current_won": c_ok, "repaired_won": r_ok,
                       "current_cost": gm.get("current", {}).get("cost_usd"),
                       "repaired_cost": gm.get("shared_repaired", {}).get("cost_usd"),
                       "current_steps": gm.get("current", {}).get("steps"),
                       "repaired_steps": gm.get("shared_repaired", {}).get("steps")})

    solv = {
        "current_success": cur.get("won", 0),
        "repaired_success": rep.get("won", 0),
        "current_by_task": {},
        "repaired_by_task": {},
    }
    for t in (0, 10, 20):
        solv["current_by_task"][str(t)] = sum(1 for e in by_rt.get("current", []) if e.get("task_index") == t and e.get("won"))
        solv["repaired_by_task"][str(t)] = sum(1 for e in by_rt.get("shared_repaired", []) if e.get("task_index") == t and e.get("won"))

    cost_cmp = {"current": cur, "shared_repaired": rep}
    ratio = (rep.get("median_cost_usd", 0) / cur["median_cost_usd"]) if cur.get("median_cost_usd") else None
    cost_cmp["median_cost_ratio_repaired_over_current"] = ratio
    cost_cmp["cost_safety_pass"] = bool(ratio is not None and ratio <= 1.5)

    loop_cmp = {
        "current_mean_loop_occurrences": cur.get("mean_loop_occurrences"),
        "repaired_mean_loop_occurrences": rep.get("mean_loop_occurrences"),
        "current_mean_repetition_ratio": cur.get("mean_repetition_ratio"),
        "repaired_mean_repetition_ratio": rep.get("mean_repetition_ratio"),
        "note": "auxiliary diagnostic — does not replace native won",
    }

    # gates
    g1 = "PASS" if rep.get("won", 0) >= 1 else "FAIL"
    if rep.get("won", 0) >= 1 and cur.get("won", 0) == 0 and rep_only >= 2:
        g2 = "PAIRED_IMPROVEMENT_SUPPORTED"
    elif rep.get("won", 0) == 0 and cur.get("won", 0) == 0:
        g2 = "REPAIR_NOT_SUPPORTED"
    elif rep.get("won", 0) == 1 and cur.get("won", 0) == 0:
        g2 = "SOLVABILITY_SIGNAL_OBSERVED_IMPROVEMENT_INCONCLUSIVE"
    else:
        g2 = "IMPROVEMENT_INCONCLUSIVE"
    g3 = "PASS" if cost_cmp["cost_safety_pass"] else "COST_SAFETY_FAIL"
    g4 = "AUXILIARY_ONLY"

    if g1 == "FAIL":
        decision = "SHARED_REPAIR_INSUFFICIENT"
    elif g2 == "PAIRED_IMPROVEMENT_SUPPORTED":
        decision = "SHARED_REPAIR_FEASIBILITY_SUPPORTED"
    elif rep.get("won", 0) >= 1:
        decision = "SOLVABILITY_OBSERVED_AB_INCONCLUSIVE"
    else:
        decision = "SHARED_REPAIR_INSUFFICIENT"

    ledger = {}
    db = OUT / "budget.sqlite"
    if db.exists():
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM budget WHERE id=1").fetchone()
        ledger = dict(r) if r else {}
        ledger["meta"] = {x["key"]: x["value"] for x in c.execute("SELECT * FROM meta")}
        c.close()

    (OUT / "ab_paired_results.json").write_text(json.dumps({
        "pairs": paired, "paired_repaired_only_wins": rep_only,
        "paired_current_only_wins": cur_only, "paired_ties": ties,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "solvability_results.json").write_text(json.dumps(solv, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "cost_comparison.json").write_text(json.dumps(cost_cmp, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "loop_comparison.json").write_text(json.dumps(loop_cmp, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "gate_decisions.json").write_text(json.dumps({
        "GATE1_REPAIRED_SOLVABILITY": {"result": g1, "repaired_success": rep.get("won", 0)},
        "GATE2_PAIRED_IMPROVEMENT": {"result": g2, "rep_only": rep_only, "cur_only": cur_only},
        "GATE3_COST_SAFETY": {"result": g3, "ratio": ratio},
        "GATE4_LOOP_REDUCTION": {"result": g4, **loop_cmp},
        "FINAL_DECISION": decision,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    summary_path = OUT / "raw_episode_summary.json"
    raw = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
    (OUT / "audit_report.json").write_text(json.dumps({
        "stage": "STAGE1_6_AB",
        "status": "COMPLETED",
        "executed_episodes": raw.get("executed_episodes", 12),
        "current_success": solv["current_success"],
        "repaired_success": solv["repaired_success"],
        "total_http": ledger.get("physical_attempts"),
        "total_tokens_in": ledger.get("tokens_in"),
        "total_tokens_out": ledger.get("tokens_out"),
        "total_cost_usd": ledger.get("spent_cost"),
        "settled_ok": ledger.get("settled_ok"),
        "settled_failed": ledger.get("settled_failed"),
        "retries": ledger.get("retries"),
        "billing_blocked": bool(ledger.get("meta", {}).get("billing_blocked")),
        "exec_git_sha": raw.get("exec_git_sha"),
        "manifest_sha256": raw.get("manifest_sha256"),
        "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": g4},
        "final_decision": decision,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print("current", json.dumps(cur, indent=2))
    print("repaired", json.dumps(rep, indent=2))
    print("paired", rep_only, cur_only, ties)
    print("GATES", g1, g2, g3, "DECISION", decision)


if __name__ == "__main__":
    main()
