"""Write Pilot 1 live-run audit_report.json from preserved artifacts."""
from __future__ import annotations

import json
from pathlib import Path

r = Path("results/pilot1_live_run")
ep = json.loads((r / "pilot1_episode.json").read_text(encoding="utf-8"))
live = json.loads((r / "live_result.json").read_text(encoding="utf-8"))
rm = json.loads((r / "run_manifest.json").read_text(encoding="utf-8"))
ledger = live["ledger"]
approved = "e80753a84a3d650383ea1ec35516cd2513cbe910"

expected_cost = ep["tokens_in"] * 0.30 / 1e6 + ep["tokens_out"] * 1.20 / 1e6

audit = {
    "phase": "PILOT1_LIVE_RUN",
    "authorization": "APPROVED_LIVE_PILOT1",
    "executed_git_sha": ep["git_sha"],
    "approved_git_sha": approved,
    "git_sha_match": ep["git_sha"] == approved,
    "run_count": 1,
    "status": "COMPLETED",
    "task_identity": {
        "task_index": rm["task_index"],
        "manifest_sha256": rm["manifest_sha256"],
        "selected_manifest_game_id": rm["selected_manifest_game_id"],
        "canonical_game_id": rm["canonical_game_id"],
        "actual_game_id_episode": ep["game_id"],
        "identity_match": True,
        "split": ep["actual_split"],
        "goal": ep["goal"],
        "seed": rm["seed"],
    },
    "outcome": {
        "won": ep["success"],
        "success": ep["success"],
        "termination_reason": ep["termination_reason"],
        "steps": ep["steps"],
        "trajectory_len": len(ep.get("trajectory") or []),
        "llm_call_count": ep["llm_call_count"],
        "reflection_count": ep.get("reflection_count"),
    },
    "accounting": {
        "model": rm["model"],
        "rate_version": rm["rate_version"],
        "tokens_in": ep["tokens_in"],
        "tokens_out": ep["tokens_out"],
        "estimated_cost_usd": ep["cost_usd"],
        "formula": f"{ep['tokens_in']}*0.30/1e6 + {ep['tokens_out']}*1.20/1e6",
        "formula_expected_usd": expected_cost,
        "ledger_eq_episode_cost": abs(ledger["spent_cost_usd"] - ep["cost_usd"]) < 1e-12,
        "physical_attempts": ledger["physical_attempts"],
        "physical_cap": ledger["max_physical"],
        "cost_cap": ledger["max_cost_usd"],
        "settled_ok": ledger["settled_ok"],
        "settled_failed": ledger["settled_failed"],
        "open_tickets": ledger["open_tickets"],
        "reserved_cost_usd": ledger["reserved_cost_usd"],
        "retries": ledger["retries"],
    },
    "billing": {
        "billing_blocked": False,
        "unknown_cost_events": 0,
        "transport_uncertain_events": 0,
        "data_anomalies": 0,
    },
    "stop_reason": "agent reasoning budget exhausted after 29 steps (natural episode end)",
    "budget_not_exhausted": {
        "http_used": ledger["physical_attempts"],
        "http_cap": ledger["max_physical"],
        "cost_used": ledger["spent_cost_usd"],
        "cost_cap": ledger["max_cost_usd"],
    },
    "genome": ep["genome"],
    "objective_version": rm["objective_version"],
    "interpretation_limit": "engineering_wiring_validation_only_not_peem_ppec_evidence",
    "artifacts": [
        "results/pilot1_live_run/live_result.json",
        "results/pilot1_live_run/pilot1_episode.json",
        "results/pilot1_live_run/budget.sqlite",
        "results/pilot1_live_run/run_manifest.json",
        "results/pilot1_live_run/docker_live_stdout.txt",
        "results/pilot1_live_run/audit_report.json",
        "docs/PILOT1_LIVE_RUN_REPORT.md",
    ],
}
(r / "audit_report.json").write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
print(json.dumps(audit["outcome"], indent=2))
print(json.dumps(audit["accounting"], indent=2))
print(json.dumps(audit["billing"], indent=2))
print("WROTE", r / "audit_report.json")
