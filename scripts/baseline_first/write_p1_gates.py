import json
from pathlib import Path

OUT = Path("results/stage3_0_p1")
(OUT / "final_gate_decisions.json").write_text(
    json.dumps(
        {
            "GATE_P1_A_FULLTEXT": "PARTIAL — AFlow method via code+abstract; others abstract-level; FULL_TEXT_NOT_VERIFIED for PDFs",
            "GATE_P1_B_SOURCE_PIN": "PASS (commit 3f457218fc716093fe53f6df8a5d5e6379d66346, MIT, external/ gitignored)",
            "GATE_P1_C_OFFICIAL_EXECUTION": "PASS at Level 2 (import + Optimizer/utils + MockLLM; LLM-gen search loop not end-to-end)",
            "GATE_P1_D_HISTORY_AUDIT": "PASS inventory; REAL_TRACE_EVIDENCE_INSUFFICIENT (all logs empty)",
            "GATE_P1_E_PILOT_READY": "PROTOCOL+BUDGET ready; not authorized",
            "FINAL_DECISION": "BASELINE_READY_GAP_UNCONFIRMED",
            "real_llm_calls": 0,
            "paper_code_divergences": [
                "MCTS claim vs top-k mixed-distribution sampling (no UCT/backprop)",
                "experience 'Absolutely prohibit' applied to successful modifications too",
            ],
        },
        indent=2,
    ),
    encoding="utf-8",
)
print("ok")
