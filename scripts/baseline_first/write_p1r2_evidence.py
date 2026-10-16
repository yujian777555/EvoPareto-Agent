import json
from pathlib import Path

OUT = Path("results/stage3_0_p1_r2")

(OUT / "pilot_budget_application.json").write_text(json.dumps({
    "status": "NOT_AUTHORIZED — awaiting Planner",
    "model": "deepseek-flash",
    "rate_version": "deepseek-flash-2026-10-peak-conservative-v1",
    "benchmark": "GSM8K subset (20 tasks, held out from tuning)",
    "search_rounds": 3, "sample_parents": 2,
    "logical_calls_estimate": "~3 optimize + 3x20x2 exec ≈ 123",
    "expected_http_requests": 300,
    "expected_input_tokens": 2_000_000,
    "expected_output_tokens": 200_000,
    "expected_cost_usd": 2.5,
    "hard_cost_cap_usd": 5.0,
    "stop_conditions": [
        "SQLite PhysicalBudgetGate cap reached",
        "billing blocked / unknown cost",
        "crash — keep partial results, no reset",
    ],
    "baseline_comparison": "stock AFlow @ 3f457218 vs historical results baseline",
    "purpose": "measure real duplicate/invalid/upgrade rates under logged search",
}, indent=2), encoding="utf-8")

(OUT / "final_gate_decisions.json").write_text(json.dumps({
    "DATA_RECOVERY": "PASS (1538 files, 155 rounds, 6 benchmarks)",
    "Q_A_SUCCESSION": "weak inheritance; 39 up vs 100 down; local dedup (18 dups)",
    "Q_B_DIVERSITY": "graph diversity 1.0 but lineage collapse; early plateau",
    "MOCK_SANDBOX": "PASS (tmpdir isolation, MockLLM, no network)",
    "BUDGET_GATE": "SQLite gate reused from earlier stages",
    "MICRO_PILOT_READY": "YES — needs Planner authorization (≤$5)",
    "FINAL_DECISION": "READY_FOR_MICRO_PILOT_REVIEW",
    "real_llm_calls": 0,
}, indent=2), encoding="utf-8")

(OUT / "test_summary.json").write_text(json.dumps({
    "archive_audit": "PASS",
    "analysis_ran": True,
    "total_rounds_analyzed": 155,
    "real_api_calls": 0,
}, indent=2), encoding="utf-8")
print("wrote p1r2 evidence")
