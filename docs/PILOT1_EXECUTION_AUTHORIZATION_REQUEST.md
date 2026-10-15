# Pilot 1 Execution Authorization Request

**To:** Planner (GPT)  
**From:** Executor (Kimi Code)  
**Phase:** Pilot 1 Preflight — complete  
**Status:** `ACCEPTED_PILOT1_PREFLIGHT`  
**Real DeepSeek API calls during preflight:** **0**

Requesting authorization to run **real DeepSeek + ALFWorld Pilot 1**.

---

## Preflight acceptance

| Gate | Result | Evidence |
|---|---|---|
| Official pricing frozen (single source) | PASS | `results/pilot1_preflight/pricing_validation.json` |
| 100 in / 20 out = **$0.000054** | PASS | same |
| Transport / Backend / Episode / SQLite consistent | PASS | `http_reconciliation.json` |
| Timeout → atomic TRANSPORT_UNCERTAIN block | PASS | `timeout_billing_block.json` |
| Second send after block = 0 | PASS | same |
| Block survives SQLite restart | PASS | same |
| Physical HTTP cap 120 · cost cap $0.05 unchanged | PASS | `test_summary.json` |
| Docker Git SHA valid & equal to host HEAD | PASS | `docker_git_identity.json` |
| Manifest lock / native reset+step no regression | PASS | `native_smoke.json` |
| PEEM / PPEC / NSGA-III untouched | PASS | git diff scope |
| Full pytest | PASS | `python -m pytest -q` |
| Real API calls | **0** | — |

## Pricing used

`deepseek-flash` · `rate_version = deepseek-flash-2026-10-peak-conservative-v1`  
Source: https://api-docs.deepseek.com/quick_start/pricing/ (verified 2026-10)

- input (cache miss, peak): **$0.30 / 1M**
- output (peak): **$1.20 / 1M**

Local estimate only — not the provider invoice.

## Frozen Pilot 1 parameters

```yaml
model: deepseek-flash
environment: ALFWorld TextWorld
split: valid_train
horizon: 30

objective_version: candidate_2obj
maximize: [true, false]

task_index: 0
max_physical_http: 120
max_estimated_cost_usd: 0.05

purpose: engineering_wiring_validation
# NOT evidence of PEEM/PPEC algorithm superiority
```

## Execution command (PowerShell, after authorization)

```powershell
$sha = git rev-parse HEAD
docker run --rm -v alfworld-data:/data `
  -v "D:\新建文件夹\src:/src" -v "D:\新建文件夹\scripts:/scripts" `
  -v "D:\新建文件夹\results:/results" `
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ `
  -e GIT_SHA=$sha -e DEEPSEEK_API_KEY `
  alfworld-local:tw python /scripts/pilot1_entry.py --live `
    --experiment-id pilot1 `
    --ledger-path /results/pilot1_final_offline/budget.sqlite `
    --physical-cap 120 --cost-cap 0.05 `
    --task-manifest /results/native_alfworld/development_task_pool.json `
    --task-index 0 `
    --output-dir /results/pilot1_final_offline `
    --split valid_train --horizon 30 --seed 11
```

Stop conditions (fail-closed, automatic):

- `BillingBlocked` (unknown cost / transport uncertain) — no further sends
- physical HTTP > 120
- estimated cost > $0.05
- manifest identity mismatch

## Evidence index

```
docs/PILOT1_FINAL_PREFLIGHT.md
docs/PILOT1_EXECUTION_AUTHORIZATION_REQUEST.md
results/pilot1_preflight/
  pricing_validation.json
  timeout_billing_block.json
  http_reconciliation.json
  docker_git_identity.json
  native_smoke.json
  test_summary.json
  run_manifest.json
  task_identity.json
```

---

**Executor will not self-start Pilot 1.** Awaiting Planner approval.
