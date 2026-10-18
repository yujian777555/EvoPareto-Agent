# Historical Cost Reconciliation (Task D)

Baseline numbers — original ledgers NOT modified.

## First run `paired-a4c26b15`

- child requests: 36
- usage cost estimate: $0.0046524
- parent requests: 0

## Full paired run `paired2-7715a4e3`

- parent requests: 12
- child requests: 37
- total: 49
- parent usage cost: $0.0017952
- child usage cost: $0.0053949
- total: $0.0071901

## R2 stage totals

- new requests: **85** / 100
- usage cost estimate: $0.0118425

## Cumulative

- R1 debited: $0.0018669
- R1+R2 debited: $0.0137094
- parent re-verification added 12 requests (~$0.0018)
- provider invoice: **NOT_VERIFIED**

Three-way billing split is maintained: budget_debited / usage_cost_estimate /
provider_invoice.
