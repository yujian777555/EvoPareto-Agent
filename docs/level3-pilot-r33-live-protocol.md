# MICRO-R3.3: guarded live GSM8K micro-pilot

## Scope boundary

This is the **separate Level3 GSM8K pilot**, not the master's thesis mainline experiment. It must not be cited as evidence that NSGA-III or the thesis's recursive self-improvement method works.

## Arms and selection

- **P**: frozen parent workflow.
- **R**: one seeded random-mutation child.
- **F**: one feedback-driven child derived from Parent development failures, if usable feedback exists.
- **E2**: a second-generation feedback child derived from the selected generation-1 winner's own development records, if usable feedback exists.
- Candidate selection uses only the 5 development tasks. The 8 confirmation tasks are held out and never select a winner.
- Parent, winner and E2 use the same confirmation task IDs. Paired outcomes and two-sided exact McNemar p-values are descriptive/exploratory only.

## Data and budget gates

- The official training JSONL must match SHA-256 17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465.
- Screening/dev/confirmation indices are checked against each other and the prior-use exclusion set.
- Hard limits: 55 physical requests, USD 0.05 charged upper bound, 1,500 conservatively estimated input tokens per request and 300 output tokens per request.
- Each request has a durable pre-send reservation and send-intent event. The append-only JSONL ledger is fsynced before the network send and after settlement.
- Timeout, HTTP error, invalid JSON, missing usage or invalid usage is fail-closed: the full per-request reservation is charged against the budget bound and the run stops.
- The request body is not truncated after its cost estimate. Prompts above the estimated input cap are rejected before send.
- DeepSeek requests explicitly bypass environment/global HTTP proxies with ProxyHandler({}).

## Run commands

Offline rehearsal (simulated evidence only):

    python scripts/level3_pilot_r4/run_micro_r33.py --mock --out results/r33_mock_UNIQUE

Real run (only when the operator has explicitly authorized it and DEEPSEEK_API_KEY is available):

    python scripts/level3_pilot_r4/run_micro_r33.py --real --out results/level3_pilot_r4_micro_r33_live

The guarded GitHub Actions run is one-shot: it only launches a real experiment for a push whose commit message contains [RUN_REAL_R3_3_ONCE], and only after offline regression passes and the repository secret exists.

## Evidence files

- protocol.json: frozen protocol, split and cap values.
- request_ledger.jsonl: append-only pre-send, send-intent, settlement and block events.
- request_ledger.json: current ledger snapshot, including unknown-billing upper bounds.
- paired_results.json: task-level development and confirmation rows.
- paired_analysis.json: paired counts and exact p-values.
- candidate_lineage.json: parent/child lineage and hashes.
- summary.json, REPORT.md: run outcome and evidence class.
- ABORTED.json / PRECHECK_BLOCKED.md: fail-closed run termination evidence.

## Interpretation

This is a single-seed, 5-development/8-confirmation micro-pilot. It can test whether the real pipeline executes and whether the observed child is directionally better on these tasks. It is not adequately powered for a confirmatory claim, does not by itself establish recursive self-improvement, and does not test NSGA-III.
