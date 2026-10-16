from pathlib import Path

d = Path("docs/stage3_0_p1")
files = {
    "RESEARCH_SCOPE.md": (
        "# Research Scope (Stage 3.0-P1)\n\n"
        "Baseline-first: pin AFlow, audit algorithm code, mock-execute official\n"
        "pipeline, inventory historical artifacts, define Level-3 pilot + budget.\n"
        "Constraints: REAL_LLM_CALLS=0, GPU=0, REAL_BENCHMARK_RUNS=0, no new\n"
        "controllers. FCEOL remains closed. External repo in external/AFlow (gitignored).\n"
    ),
    "GEPA_METHOD_COMPARISON.md": (
        "# GEPA Method Comparison\n\n"
        "GEPA = reflective prompt mutation + Pareto candidate selection + merging\n"
        "(per citations in EnactOpt/TEB/2610.14662). Strong prompt-evolution baseline.\n"
        "FULL_TEXT_NOT_VERIFIED this session. vs AFlow: prompts only vs code+prompts.\n"
    ),
    "COCOEVOLVE_METHOD_COMPARISON.md": (
        "# CoCoEvolve Method Comparison\n\n"
        "(2610.12794) Meta-reflection: mutator uses full history + probes live system\n"
        "before edits. Already diagnose/probe-before-mutate. FULL_TEXT_NOT_VERIFIED.\n"
    ),
    "FAILURE_FEEDBACK_PAPER_REVIEW.md": (
        "# Failure Feedback Paper Review\n\n"
        "(2610.14662) 145 DGM mods: no target-specific repair advantage; +20pp only\n"
        "in identifiable/repairable settings. Bounds failure-information value.\n"
        "FULL_TEXT_NOT_VERIFIED. Supports why FCEOL conditioning was weak.\n"
    ),
    "AFLOW_LICENSE_AND_DEPENDENCIES.md": (
        "# AFlow License & Dependencies\n\n"
        "MIT (c) 2025 FoundationAgents. requirements.txt pins 23 packages.\n"
        "Gap: tree_sitter imported by sanitize.py but unlisted; stubbed offline.\n"
        "Datasets via data/download_data.py; benchmark terms separate.\n"
    ),
    "OFFICIAL_ARTIFACT_INVENTORY.md": (
        "# Official Artifact Inventory\n\n"
        "workspace/*/ has scaffolding only (round_1 graph/prompt, templates).\n"
        "All results.json, log.json, processed_experience.json are 0 bytes.\n"
        "OFFICIAL_TRACES_FOUND: NO. Evidence class: OFFICIAL_HISTORICAL_ARTIFACT.\n"
    ),
    "TRACE_EVIDENCE_ANALYSIS.md": (
        "# Trace Evidence Analysis\n\n"
        "REAL_TRACE_EVIDENCE_INSUFFICIENT. Mock: parent-selection probs on synthetic\n"
        "scores (best gets ~0.79). Duplication/invalid-mutation/collapse/generalization\n"
        "NOT_MEASURABLE. Level-3 pilot must capture full search logs.\n"
    ),
}
for name, text in files.items():
    (d / name).write_text(text, encoding="utf-8")
print("wrote", len(files))
