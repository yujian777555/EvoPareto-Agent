# Phase5-R3-R2 — Native Setup

**Status: `NATIVE_TEXTWORLD_READY`**

## Environment

| item | value |
|------|-------|
| Host | Windows + Docker Desktop 29.3.1 |
| Image | `python:3.10-slim` → `alfworld-local:tw` |
| ALFWorld | **0.4.2** |
| TextWorld | **1.7.0** |
| Jericho | 3.3.1 |
| Data | `json_2.1.1` (train/valid_seen/valid_train/valid_unseen) + `logic/` |
| Games | **4027** `game.tw-pddl` |
| Volume | `alfworld-data` → `/data` |

## Install path (reproducible)

```text
1. docker run python:3.10-slim
2. apt-get install build-essential swig
3. pip install alfworld -i https://pypi.org/simple
4. scripts/download_alfworld_tw.py   # skips visual MRCNN
5. docker commit → alfworld-local:tw
```

Windows native pip fails (`jericho` needs `make`/`swig`). WSL2 lacked `python3-venv`/`make`.

## Smoke evidence

```text
AlfredTWEnv init → 134 OOD games
reset → TextWorld observation ("Welcome to TextWorld, ALFRED!")
admissible_commands → ['go to armchair 1', ...]
step('go to armchair 1') → new obs "You arrive at armchair 1..."
done=False, score=0, won=False
SMOKE_OK
```

## Commands

```bash
docker run --rm -v alfworld-data:/data -v $PWD/scripts:/scripts \
  -e ALFWORLD_DATA=/data alfworld-local:tw \
  python /scripts/alfworld_tw_smoke.py
```
