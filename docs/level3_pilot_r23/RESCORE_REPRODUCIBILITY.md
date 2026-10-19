# Rescore Reproducibility (Task C)

## Fixes

1. Hardcoded `D:/新建文件夹` replaced with `Path(__file__).resolve().parents[2]`.
2. Full mapping verification before scoring:
   - 12 ledger rows ↔ 12 tasks, sequential order
   - physical request IDs unique
   - Run ID consistent
   - token + prompt SHA fields present
   - cross-check `parent_reverification_results.json` `ipc_processed == 1`
     and task-id order
   - child frozen results: unique ids, full coverage, order match
3. Mapping conflicts / hash mismatches / missing results → stop scoring.
4. Path independence verified: script copied to a fake repo layout, run from
   an unrelated cwd → `PATH_INDEPENDENT_OK`.

## Results unchanged (from complete provider FULL_CONTENT)

| | correct | total |
|---|---:|---:|
| Parent | **11** | 12 |
| Child | **11** | 12 |

improved 0 ·
regressed 0 ·
both_correct 11 ·
both_wrong 1 ·
net_gain **0**

## Input / output SHAs

{
  "rescore_from_ledger.json": "6bb4b3f96de6a2292299c2e2b0cdf8c1939de68327183167d4858988eddfcc1c",
  "parentre_ledger_parentre-8aa3d61f.json": "06d4a4ce9ff93b6f961a8cd8c98c811f610e98ed4df1f00ffb0011ec1a4e250b",
  "parent_reverification_results.json": "68b07de826dfd74188899803e4888c1dcdd03f3449e1628d08333e080e1895b6",
  "paired_confirmation_set.json": "52fcc5dfdb17c9ad0cba37d8efe88e35e883b7a7bda795ee7b056654ac5671b9",
  "paired_experiment_results_corrected.json": "f21e92e661edeae8cc5daff0a73d2b93de8e9cfedbbf6c37e59dfc71522abb67"
}
