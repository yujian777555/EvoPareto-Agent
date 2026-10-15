# Pilot 1 Execution Plan

## Prerequisites (Planner approval required)

```bash
export DEEPSEEK_API_KEY=...   # not in repo
# optional proxy if needed:
# export HTTPS_PROXY=... ; export EVO_USE_PROXY=1
```

## Dry-run (already verified, 0 API)

```bash
python scripts/pilot1_entry.py --dry-run \
  --experiment-id pilot1 \
  --ledger-path results/pilot1_hotfix_offline/budget.sqlite \
  --physical-cap 120 --cost-cap 0.05 \
  --task-manifest results/native_alfworld/development_task_pool.json \
  --output-dir results/pilot1_hotfix_offline \
  --split valid_train --horizon 30 --seed 11
```

Result: `results/pilot1_hotfix_offline/dry_run.json` — all checks true
(`alfworld_importable=false` on Windows host; use Docker image `alfworld-local:tw`).

## Live (Docker, after Planner approval)

```bash
docker run --rm \
  -v alfworld-data:/data \
  -v $PWD/src:/src -v $PWD/scripts:/scripts -v $PWD/results:/results \
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ \
  -e DEEPSEEK_API_KEY \
  alfworld-local:tw \
  python /scripts/pilot1_entry.py --live \
    --experiment-id pilot1 \
    --ledger-path /results/pilot1_hotfix_offline/budget.sqlite \
    --physical-cap 120 --cost-cap 0.05 \
    --task-manifest /results/native_alfworld/development_task_pool.json \
    --output-dir /results/pilot1_hotfix_offline \
    --split valid_train --horizon 30 --seed 11
```

## Guards

`--live` required; API key; strict BudgetDB gate; caps 120 HTTP / $0.05;
stop on 402/401; full episode trace; git SHA recorded by launcher meta.

## Scope

**Pilot 1 = engineering wiring only** — not paper performance tables.
