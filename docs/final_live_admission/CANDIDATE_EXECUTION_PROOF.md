# Candidate Execution Proof (Task B)

**SAME_CANDIDATE_PROVEN = True**

| Artefact | SHA-256 |
|---|---|
| Optimizer candidate graph.py | `d4c8ac1f33dcf4ab757f7c755117fa81aed50dc35809c345b698bba93e3bb7ce` |
| Optimizer candidate prompt.py | `c716e47e8e70b18f3078ff1140280f486c480c8e860f6ee1f4356bf424f87f2d` |
| Executed child graph bytes | `d4c8ac1f33dcf4ab757f7c755117fa81aed50dc35809c345b698bba93e3bb7ce` |

The Docker child executed **the same graph.py bytes** the official Optimizer
wrote through `graph_utils.write_graph_files` — not a hand-written stand-in.

## Real Mock HTTP + gateway ledger

| Metric | Value |
|---|---:|
| REAL_MOCK_HTTP_POST_COUNT | 2 |
| GATEWAY_LEDGER_COUNT | 2 |
| physical_attempts | 2 |
| spent_cost_usd | 0.0020180999999999997 |

Every LLM call is a real HTTP POST to the local Mock Provider through
`GatewayLLM` + `PhysicalBudgetGate`. `GoldAwareMockLLM._http_chat` short-circuit
was removed.

## Official persistence (not hand-written)

| Path | Value |
|---|---|
| OFFICIAL_EXPERIENCE_PATH | `workspace/GSM8K/workflows/round_2/experience.json` |
| OFFICIAL_EXPERIENCE_FIELDS | ['after', 'before', 'father node', 'modification', 'succeed'] |
| OFFICIAL_RESULTS_PATH | `workspace/GSM8K/workflows/results.json` |

`experience.json` is written by AFlow `experience_utils.update_experience`;
`results.json` by `data_utils.save_results`. No experiment script fabricates
these files.

## Replacement boundary

| Component | Replacement | Why |
|---|---|---|
| `AsyncLLM` | `GatewayLLM` | budget gate + mock HTTP |
| `Evaluator` | `TrustedHostEvaluator` | gold-blind Docker+IPC run, host scoring |
| model in container | `ModelIPCClient` | controlled mailbox under `--network none` |

AFlow `Optimizer.optimize`, `select_round`, `write_graph_files`, `load_graph`,
`create_experience_data`, `update_experience`, `save_results` are official.
