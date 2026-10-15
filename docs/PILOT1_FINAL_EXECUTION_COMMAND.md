# Pilot1 Final Execution Command

## Dry-run (verified, 0 API)

```bash
python scripts/pilot1_entry.py --dry-run \
  --experiment-id pilot1 --ledger-path results/pilot1_final_offline/budget.sqlite \
  --physical-cap 120 --cost-cap 0.05 \
  --task-manifest results/native_alfworld/development_task_pool.json \
  --output-dir results/pilot1_final_offline --split valid_train --horizon 30 --seed 11
```

## Native offline smoke (verified in Docker)

See `PILOT1_NATIVE_DOCKER_SMOKE.md`.

## Live (awaiting Planner approval only)

```bash
docker run --rm -v alfworld-data:/data \
  -v $PWD/src:/src -v $PWD/scripts:/scripts -v $PWD/results:/results \
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ -e DEEPSEEK_API_KEY \
  alfworld-local:tw python /scripts/pilot1_entry.py --live \
  --experiment-id pilot1 --ledger-path /results/pilot1_final_offline/budget.sqlite \
  --physical-cap 120 --cost-cap 0.05 \
  --task-manifest /results/native_alfworld/development_task_pool.json \
  --output-dir /results/pilot1_final_offline --split valid_train --horizon 30 --seed 11
```

Guards: `--live`, API key, strict gate, caps 120/$0.05, stop on 402/401.
