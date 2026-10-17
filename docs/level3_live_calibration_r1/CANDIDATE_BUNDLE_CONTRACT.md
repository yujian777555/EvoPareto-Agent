# Candidate Bundle Contract (Task A)

## Problem

The real Optimizer returned `<prompt>` as **plain text**:

```
You are a careful math solver. Break problems into explicit sub-steps...
```

The official AFlow runtime imports `prompt.py` as a Python module and the
generated `graph.py` reads a module-level `INSTRUCTION`. Compiling the raw
plain text failed (`prompt_compile: FAIL:invalid syntax`), so `INSTRUCTION`
was undefined in the container.

## Contract

```
prompt.py  ->  INSTRUCTION = repr(prompt_text)
```

- Deterministic serialisation; **graph bytes are never rewritten**
- Already-valid Python modules with `INSTRUCTION` pass through verbatim
- Compile/load/dependency failures are raised **before** Docker execution

## Hashes (real Level 3 candidate)

| Artefact | SHA-256 |
|---|---|
| ORIGINAL_GRAPH_SHA | `ec852e928b06afdbfcc5af2c7134b720f928bd7eeac0e939f9ae10dc20edd50a` |
| PROMPT_RAW_SHA | `e8263cbafae3639a1e2074938394e0eda11abc9f4922ce6cd0273cea392f07f2` |
| PROMPT_MODULE_SHA | `ce140c32eef75075f150cedf86ce3bec7d5980b8af6d3e5cdcf7a6c95ed617f2` |
| BUNDLE_SHA | `a498ab9602c49962170d393d325cd548e8c2a25d48bafc25304061bb1c6a8692` |

`graph_rewritten = False` — the graph source executed in Docker is the same
bytes saved from the live run.

## Loader binding (not a rewrite)

When the real graph references a bare `INSTRUCTION`, the container runner
imports `prompt.py` and binds `graph.INSTRUCTION = prompt_module.INSTRUCTION`.
The graph file itself is untouched.

## Negative tests

{
  "missing_prompt": "REJECTED:PROMPT_FIELD_EMPTY",
  "invalid_python": "REJECTED:GRAPH_SYNTAX_INVALID:invalid syntax",
  "missing_workflow": "REJECTED:GRAPH_MISSING_WORKFLOW_CLASS",
  "wrong_dependency": "PASS_EXEC_FAILED",
  "wrong_dependency_stderr": "ine 10, in <module>\n    import graph as _g\n  File \"/work/graph.py\", line 1, in <module>\n    import module_that_does_not_exist_xyz\nModuleNotFoundError: No module named 'module_that_does_not_exist_xyz'\n"
}
