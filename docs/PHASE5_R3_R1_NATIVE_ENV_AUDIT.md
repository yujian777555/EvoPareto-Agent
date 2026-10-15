# Phase5-R3-R1 — Native ALFWorld Environment Audit

**Status: `NATIVE_ENV_BLOCKED`**

## Attempted install

```text
OS: Windows 10/11, Python 3.10.13
pip install alfworld                          # proxy index failure
pip install --index-url https://pypi.org/simple alfworld
```

**Result:** `metadata-generation-failed` (WinError 2 during package build;
ALFWorld expects game data / ai2thor / Linux-oriented deps).

## Current adapter reality

`src/benchmark/alfworld_real.py` / `webshop_real.py`:

```text
Task template → LLM text → keyword coverage + genome capability prior → success
```

There is **no** `env.reset() / env.step()`, no THOR simulator, no official
ALFWorld scoring script.

## Native integration target (not implemented)

```text
Genome → BehavioralAgent/LLM policy → Native ALFWorld env
  → observation → action → ... → env success → TaskResult
```

## Reproduction of install failure

```bash
python -c "import sys; print(sys.version)"
pip install --index-url https://pypi.org/simple alfworld
# -> metadata-generation-failed, WinError 2
```

## Conclusion

- **Real-environment validation capability: NOT available** in this workspace.
- Must not claim native ALFWorld/WebShop success.
- Existing tables classified `simulated` / `real_llm_proxy` only.

## Unblock options (for Planner)

1. Linux + official ALFWorld README (game data download, ai2thor, Docker).
2. Pre-built env container with `alfworld` installed.
3. Then implement `src/benchmark/native_alfworld.py` with reset/step/success.
