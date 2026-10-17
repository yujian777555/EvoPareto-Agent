# Candidate Bundle Reliability (Task D)

## Fixes

1. **prompt_contract type misjudge** — previously both serialised and
   passthrough modules matched `INSTRUCTION = '...'` and were labelled
   `PASSTHROUGH`. Now the function returns an explicit kind:
   `SERIALISED_INSTRUCTION_REPR` vs `PASSTHROUGH_PYTHON_MODULE`.
2. **Compile vs load** — a module can compile yet fail at `exec` (e.g.
   `INSTRUCTION = undefined_name`). `build_bundle` now actually loads the
   module and requires an `INSTRUCTION` **string** module-level binding.
3. **Dependency errors attributed** — a graph with a bad import fails in Docker
   with `ModuleNotFoundError` recorded; the candidate is never swapped for a
   hand-written success.
4. **Graph SHA preserved** — `graph_src` bytes are executed verbatim.

## Not in scope

No rewrite of the execution framework; no modification of the real model's
graph source.
