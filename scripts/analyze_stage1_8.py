"""Stage 1.8 result analysis."""
from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results/stage1_8"
EPDIR = OUT / "episodes"


def loop_stats(ep):
    traj = ep.get("trajectory") or []
    n = len(traj)
    if not n:
        return {"steps": 0, "loop_occ": 0, "rep_ratio": 0.0}
    acts = [str(t.get("action") or "") for t in traj]
    pair_c = Counter((str(t.get("observation_before") or "").strip(), a) for a, t in zip(acts, traj))
    return {
        "steps": n,
        "loop_occ": sum(c - 1 for c in pair_c.values() if c > 1),
        "rep_ratio": 1.0 - len(set(acts)) / n,
    }


def progress_flags(ep, task_index):
    logs = ep.get("decision_logs") or []
    acts = [str(d.get("executed_action") or "") for d in logs] or [
        str(t.get("action") or "") for t in (ep.get("trajectory") or [])]
    act_l = [a.lower() for a in acts]
    target = {0: "book", 10: "laptop", 20: "alarmclock"}.get(task_index, "")
    return {
        "target_discovered": any(target and target in a for a in act_l) or any(
            target and target in str(t.get("observation_after") or "").lower()
            for t in (ep.get("trajectory") or [])
        ),
        "target_acquired": any(target and target in a and a.startswith(("take", "pick")) for a in act_l),
        "tool_used": any(a.startswith("use ") and "lamp" in a for a in act_l),
        "placement_attempted": any(a.startswith(("move", "put")) and target in a for a in act_l) if target else False,
    }


def main():
    summary_path = OUT / "raw_episode_summary.json"
    raw = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = raw.get("episodes") or []
    by_rt = defaultdict(list)
    for r in rows:
        by_rt[r.get("runtime_variant") or "current"].append(r)

    def agg(items):
        if not items:
            return {}
        costs = [float(x.get("cost_usd") or 0) for x in items]
        wins = sum(1 for x in items if x.get("won"))
        loops = [loop_stats(json.loads((EPDIR / f"{x['episode_id']}.json").read_text(encoding="utf-8")))
                 for x in items]
        return {
            "n": len(items), "won": wins,
            "mean_steps": sum(int(x.get("steps") or 0) for x in items) / len(items),
            "mean_cost_usd": sum(costs) / len(costs),
            "mean_tokens_in": sum(int(x.get("tokens_in") or 0) for x in items) / len(items),
            "mean_tokens_out": sum(int(x.get("tokens_out") or 0) for x in items) / len(items),
            "mean_http": sum(int(x.get("llm_call_count") or 0) for x in items) / len(items),
            "mean_loop_occ": sum(l["loop_occ"] for l in loops) / len(loops),
            "cost_per_success": (sum(costs) / wins) if wins else None,
        }

    cur = agg(by_rt.get("current", []))
    grd = agg(by_rt.get("grounded_planner_v1", []))

    paired = []
    by_cell = defaultdict(dict)
    for r in rows:
        by_cell[r.get("task_index")][r.get("runtime_variant")] = r
    g_only = c_only = both_win = both_fail = 0
    for t, gm in sorted(by_cell.items()):
        c_ok = bool(gm.get("current", {}).get("won"))
        g_ok = bool(gm.get("grounded_planner_v1", {}).get("won"))
        if g_ok and not c_ok:
            g_only += 1
        elif c_ok and not g_ok:
            c_only += 1
        elif c_ok and g_ok:
            both_win += 1
        else:
            both_fail += 1
        paired.append({"task_index": t, "current_won": c_ok, "grounded_won": g_ok})

    planning = []
    for r in rows:
        ep = json.loads((EPDIR / f"{r['episode_id']}.json").read_text(encoding="utf-8"))
        pf = progress_flags(ep, r.get("task_index"))
        ls = loop_stats(ep)
        planning.append({
            "episode_id": r["episode_id"], "runtime_variant": r["runtime_variant"],
            "won": bool(r.get("won")), **pf, **ls,
            "termination_reason": r.get("termination_reason"),
            "subgoal_transitions": len((ep.get("repaired_state") or {}).get("goal_state") or {}) if r.get("runtime_variant") != "current" else None,
        })

    ledger = {}
    db = OUT / "budget.sqlite"
    if db.exists():
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM budget WHERE id=1").fetchone()
        ledger = dict(r) if r else {}
        ledger["meta"] = {x["key"]: x["value"] for x in c.execute("SELECT * FROM meta")}
        c.close()

    gate1 = "GROUNDED_SOLVABILITY_SIGNAL_OBSERVED" if grd.get("won", 0) >= 1 else "GROUNDED_SOLVABILITY_NOT_ESTABLISHED"
    if g_only >= 1 and grd.get("won", 0) >= 1:
        gate2 = "EXPLORATORY_POSITIVE_COMPARISON"
    elif c_only >= 1 and grd.get("won", 0) == 0:
        gate2 = "CURRENT_BETTER_INVESTIGATE_PLANNER_INTERFERENCE"
    else:
        gate2 = "BOTH_FAIL" if both_fail >= 1 else "INCONCLUSIVE"

    (OUT / "paired_results.json").write_text(json.dumps({
        "pairs": paired, "grounded_only_wins": g_only, "current_only_wins": c_only,
        "both_win": both_win, "both_fail": both_fail,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "planning_behavior.json").write_text(json.dumps({
        "rows": planning,
        "note": "auxiliary mechanism metrics — native won is the only performance",
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "cost_comparison.json").write_text(json.dumps({
        "current": cur, "grounded_planner_v1": grd,
        "total_http": ledger.get("physical_attempts"),
        "total_tokens_in": ledger.get("tokens_in"),
        "total_tokens_out": ledger.get("tokens_out"),
        "total_estimated_cost_usd": ledger.get("spent_cost"),
        "cost_per_success_current": cur.get("cost_per_success"),
        "cost_per_success_grounded": grd.get("cost_per_success"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    decision = (
        "GROUNDED_SOLVABILITY_SIGNAL_OBSERVED" if grd.get("won", 0) >= 1
        else "GROUNDED_SOLVABILITY_NOT_ESTABLISHED"
    )
    (OUT / "gate_decisions.json").write_text(json.dumps({
        "GATE1_SOLVABILITY": gate1,
        "GATE2_RELATIVE": gate2,
        "GATE3_COST": "REPORTED",
        "GATE4_PLANNING_BEHAVIOR": "AUXILIARY_REPORTED",
        "FINAL_DECISION": decision,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (OUT / "audit_report.json").write_text(json.dumps({
        "stage": "STAGE1_8", "status": "COMPLETED",
        "executed_episodes": raw.get("executed_episodes"),
        "current_success": raw.get("current_success"),
        "grounded_success": raw.get("grounded_success"),
        "total_http": ledger.get("physical_attempts"),
        "total_cost_usd": ledger.get("spent_cost"),
        "settled_ok": ledger.get("settled_ok"),
        "retries": ledger.get("retries"),
        "billing_blocked": bool(ledger.get("meta", {}).get("billing_blocked")),
        "exec_git_sha": raw.get("exec_git_sha"),
        "final_decision": decision,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    print("current", json.dumps(cur, indent=2))
    print("grounded", json.dumps(grd, indent=2))
    print("paired", g_only, c_only, both_win, both_fail)
    print("GATE1", gate1, "GATE2", gate2, "DECISION", decision)


if __name__ == "__main__":
    main()
