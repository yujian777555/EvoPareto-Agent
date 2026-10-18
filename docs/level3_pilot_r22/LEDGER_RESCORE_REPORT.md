# Ledger-based Rescore Report (Task A)

**Evidence class: DERIVED_FROM_EXISTING_LEDGER** — 0 real API calls.

## Source

Scored from the complete `FULL_CONTENT` fields in
`parentre_ledger_parentre-8aa3d61f.json`. The container stdout
`repr(out)[:500]` is **not** used as a scoring source.

## Task mapping verification

12 ledger rows · 12 confirmation tasks · sequential order ·
each row `parent_ipc` with one IPC call · `finish_reason=stop` · `http=200`.
Mapping verified — not guessed.

## Results (matches Planner's independent expectation)

| | Parent | Child |
|---|---:|---:|
| correct | **11** / 12 | **11** / 12 |
| accuracy | 0.917 | 0.917 |

Paired: improved **0**,
regressed **0**,
both correct **11**,
both wrong **1**,
net gain **0**.

**Parent and child are TIED at 11/12.** The only wrong task is
`gsm8k-test-0004` (parent predicted 17, gold 19; child also wrong).

`gsm8k-test-0006` is correctly scored **True** from the full response
(`\boxed{70000}`) — the earlier truncation-based score of False was wrong.

## Per-task evidence

Each parent row records: task_id, ledger row index, physical_request_id,
prompt_sha256, **full_response_sha256**, full_response_len, finish_reason,
http_status, usage tokens, gold, predicted, correctness.

## Three-way cost split

| Column | Meaning |
|---|---|
| budget_debited_usd | conservative authorization charge |
| usage_cost_estimate_usd | provider usage × configured prices |
| provider_invoice_cost_usd | **NOT_VERIFIED** |

## Source file SHAs

{
  "parentre_ledger_parentre-8aa3d61f.json": "06d4a4ce9ff93b6f961a8cd8c98c811f610e98ed4df1f00ffb0011ec1a4e250b",
  "paired_confirmation_set.json": "52fcc5dfdb17c9ad0cba37d8efe88e35e883b7a7bda795ee7b056654ac5671b9",
  "paired_experiment_results_corrected.json": "f21e92e661edeae8cc5daff0a73d2b93de8e9cfedbbf6c37e59dfc71522abb67",
  "rescore_from_ledger.json": "14c1181c61b60f5a13db8ded0592af17fc9bfa0c94bb25a090a8fd8d45835421",
  "parent_reverification_results.json": "68b07de826dfd74188899803e4888c1dcdd03f3449e1628d08333e080e1895b6"
}
