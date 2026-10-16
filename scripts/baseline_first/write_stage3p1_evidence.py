"""Write Stage 3.0-P1 structured evidence."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "results/stage3_0_p1"
OUT.mkdir(parents=True, exist_ok=True)
AFLOW = ROOT / "external" / "AFlow"

sha = subprocess.check_output(["git", "-C", str(AFLOW), "rev-parse", "HEAD"]).decode().strip()

(OUT / "official_source_manifest.json").write_text(json.dumps({
    "repository_url": "https://github.com/FoundationAgents/AFlow",
    "upstream_commit_sha": sha,
    "branch_or_tag": "main (shallow clone depth=1)",
    "license": "MIT (Copyright 2025 FoundationAgents)",
    "python_version_required": "3.x (openai>=1.82, pydantic, pandas, numpy)",
    "dependencies": "requirements.txt (23 pinned pkgs); tree_sitter NOT in requirements but imported by scripts/utils/sanitize.py",
    "benchmark_versions": "GSM8K, MATH, DROP, HotpotQA, HumanEval, MBPP, BBH, GPQA, LiveCodeBench, etc. (download via data/download_data.py)",
    "external_submodules": "none observed at top level",
    "pinned": True,
    "location": "external/AFlow (gitignored, not vendored)",
}, indent=2), encoding="utf-8")

(OUT / "dependency_manifest.json").write_text(json.dumps({
    "tree_sitter": "MISSING in offline env; imported by scripts/utils/sanitize.py only; stubbed for import smoke — DEPENDENCY_INCOMPATIBILITY",
    "openai": "required at runtime for real LLM; NOT exercised (MockLLM)",
    "network": "denied this round",
}, indent=2), encoding="utf-8")

(OUT / "source_code_map.json").write_text(json.dumps({
    "entry": "run.py → Optimizer.optimize",
    "optimizer.py": "iterative rounds: top-k sample parent → LLM GraphOptimize(modification,graph,prompt) → check_modification → evaluate → update_experience → check_convergence",
    "parent_selection": "data_utils.select_round: mixed_prob = λ·uniform + (1-λ)·softmax(α·score), α=0.2 λ=0.3, over top-k rounds (default sample)",
    "expansion_generation": "optimize_llm prompt includes graph code + prompt + operator descriptions + formatted experience; output is new graph/prompt Python",
    "evaluation": "evaluation_utils.evaluate_graph over validation_rounds samples; score = avg",
    "backpropagation": "NONE in classic MCTS sense — scores stored per round; no tree edge updates",
    "experience": "experience_utils: per-father-node success/failure lists; formatted as 'Absolutely prohibit <modification>' for BOTH success and failure; exact-string dedup via check_modification",
    "workflow_representation": "Python class Workflow with Operator calls (Custom, ScEnsemble, Programmer, AnswerGenerate...) + prompt.py; LLM edits both structure and prompts",
    "convergence": "convergence_utils.check_convergence(top_k=3)",
    "operators_available": ["Custom","AnswerGenerate","ScEnsemble","MdEnsemble","Programmer/CustomCodeGenerate","Review","Revise","ReflectionTest","Format","Generate"],
    "paper_code_note": "Paper frames MCTS; code implements top-k mixed-distribution sampling + LLM edit + experience dedup — no UCT tree search. Marked PAPER_CODE_DIVERGENCE (implementation simplification, not necessarily a bug).",
}, indent=2), encoding="utf-8")

(OUT / "compatibility_audit.json").write_text(json.dumps({
    "UPSTREAM_IMPLEMENTATION": "AFlow @ " + sha,
    "DEPENDENCY_INCOMPATIBILITY": "tree_sitter imported but not in requirements.txt; offline pip blocked (proxy)",
    "ENVIRONMENT_ERROR": "none after stub",
    "BENCHMARK_ERROR": "data/ download required for real eval — not run",
    "MODEL_PROVIDER_ERROR": "none (MockLLM; AsyncOpenAI not instantiated)",
    "ALGORITHM_LIMITATION": "experience dedup is exact-string only; 'Absolutely prohibit' applied to successes too",
    "patches_applied_to_upstream": "none",
}, indent=2), encoding="utf-8")

# check for any non-empty official traces
traces = []
for p in (AFLOW / "workspace").rglob("*"):
    if p.is_file() and p.suffix in (".json", ".jsonl") and p.stat().st_size > 0:
        traces.append(str(p.relative_to(AFLOW)))
(OUT / "historical_artifact_inventory.json").write_text(json.dumps({
    "official_artifacts_found": True,
    "scaffolding": ["workspace/*/workflows/round_1/graph.py", "prompt.py", "template/operator*.py"],
    "results_json_all_empty": True,
    "logs_all_empty": True,
    "processed_experience_all_empty": True,
    "nonempty_json_files": traces,
    "official_traces_found": False,
    "evidence_class": "OFFICIAL_HISTORICAL_ARTIFACT (scaffolding only)",
    "note": "no intermediate search rounds, no scores, no candidate records — REAL_TRACE_EVIDENCE_INSUFFICIENT",
}, indent=2), encoding="utf-8")

(OUT / "trace_analysis.json").write_text(json.dumps({
    "REAL_TRACE_ANALYSIS": "REAL_TRACE_EVIDENCE_INSUFFICIENT",
    "MOCK_TRACE_ANALYSIS": "see mock_smoke_results.json (selection probabilities observed)",
    "search_duplication": "NOT_MEASURABLE (no traces)",
    "invalid_mutation": "NOT_MEASURABLE",
    "search_branch_collapse": "NOT_MEASURABLE",
    "failure_feedback_use": "code-level: failure mods formatted as 'Absolutely prohibit'; exact-string dedup only",
    "generalization_evidence": "NOT_AVAILABLE in repo artifacts",
}, indent=2), encoding="utf-8")

(OUT / "mock_execution_trace.json").write_text(json.dumps({
    "steps": [
        "stub tree_sitter → import scripts.optimizer, data_utils, experience_utils, workflow",
        "DataUtils.select_round on synthetic scores [50,80,60] → mixed probs [0.786,0.113,0.102] biased to best",
        "ExperienceUtils.load_experience + format_experience + check_modification",
        "Optimizer constructed with MockLLM (no AsyncOpenAI)",
        "GraphOptimize pydantic serialization",
    ],
    "network_isolation": "MockLLM only; no sockets opened",
    "sandbox": "no untrusted generated code executed this round",
}, indent=2), encoding="utf-8")

(OUT / "baseline_reproducibility_gates.json").write_text(json.dumps({
    "LEVEL_1_IMPORT": "PASS",
    "LEVEL_2_MOCK_PIPELINE": "PASS (Optimizer + utils exercised; full search loop with LLM-gen not run end-to-end)",
    "LEVEL_3_NATIVE_PILOT": "NOT_EXECUTED",
    "LEVEL_4_PAPER_SCALE": "NOT_EXECUTED",
}, indent=2), encoding="utf-8")

(OUT / "pilot_budget_estimate.json").write_text(json.dumps({
    "assumptions": "AFlow search: per round ~1 optimize-LLM call + validation_rounds×tasks execute-LLM calls; execute calls ~1-4 LLM calls/task depending on workflow",
    "minimum_pilot": {
        "model": "deepseek-flash (or paper-equivalent small model)",
        "benchmark": "GSM8K subset",
        "candidates": 5, "tasks_per_eval": 20, "search_depth_rounds": 5,
        "logical_model_calls": "~5 optimize + 5×20×2 exec ≈ 205",
        "physical_http": "≤ 300 (retries/failures)",
        "input_tokens": "~1.5M", "output_tokens": "~0.3M",
        "estimated_cost": "$0.6–1.5",
    },
    "normal_pilot": {
        "benchmark": "GSM8K + HumanEval",
        "candidates": 10, "tasks_per_eval": 50, "rounds": 10,
        "logical_model_calls": "~10 + 10×50×2 ≈ 1010",
        "physical_http": "≤ 1500",
        "estimated_cost": "$5–12",
    },
    "worst_case_bound": {
        "physical_http": "≤ 3000", "estimated_cost": "$25",
        "hard_cap": 30.0,
        "fail_closed": "SQLite PhysicalBudgetGate; stop on cap; no reset",
    },
    "uncertainty": "token per call varies with workflow length; cache/retry billing unknown; rates from deepseek-flash-2026-10-peak-conservative",
    "note": "BUDGET_ESTABLISHED_PROVISIONAL — needs Planner approval before Level 3",
}, indent=2), encoding="utf-8")

print("AFlow commit", sha)
print("wrote stage3_0_p1 evidence")
