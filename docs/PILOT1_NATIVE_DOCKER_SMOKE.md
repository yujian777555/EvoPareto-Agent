# Pilot1 Native Docker Smoke

```bash
docker run --rm \
  -v alfworld-data:/data \
  -v $PWD/src:/src -v $PWD/scripts:/scripts -v $PWD/results:/results \
  -e ALFWORLD_DATA=/data -e PYTHONPATH=/ -e GIT_SHA=575346d \
  alfworld-local:tw python /scripts/native_offline_smoke.py
```

**Result:** `native_dry_run_status=PASS`  
- game: `.../valid_train/look_at_obj_in_light-Bowl-None-DeskLamp-316/...`  
- goal: “look at bowl under the desklamp.”  
- success=false (Mock LLM) · `won` from native env  
- fitness `[0.0, 0.0]` valid `candidate_2obj`  
- manifest sha256 recorded
