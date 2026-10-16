# Official Mock Execution Report

Command: `python scripts/baseline_first/aflow_mock_smoke.py`

| Check | Result |
|---|---|
| STATIC_IMPORT_TEST | PASS (with tree_sitter stub) |
| OFFICIAL_WORKFLOW_LOAD | PASS (Workflow base + template graph) |
| OFFICIAL_OPERATOR_EXECUTION | PASS (`select_round` + mixed probs) |
| MOCK_PROVIDER_INJECTION | PASS (experience format + dedup) |
| SEARCH_LOOP_SMOKE | PASS (Optimizer constructed; `get_top_rounds`) |
| RESULT_SERIALIZATION | PASS (GraphOptimize) |
| TRACE_CAPTURE | partial (in-process only) |
| NETWORK_ISOLATION | PASS (MockLLM; no sockets) |

**Limit:** full LLM-generated search loop (`_optimize_graph` with real
generation) **not** executed end-to-end — `SEARCH_LOOP_NOT_FULLY_EXECUTED`.
No untrusted generated code executed; no sandboxed graph.py runs this round.
