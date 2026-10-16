# AFlow Source Pin

**Pinned YES.**

| Field | Value |
|---|---|
| repository_url | https://github.com/FoundationAgents/AFlow |
| upstream_commit_sha | `3f457218fc716093fe53f6df8a5d5e6379d66346` |
| branch_or_tag | main (shallow clone depth=1) |
| license | **MIT** (Copyright 2025 FoundationAgents) |
| python | 3.x; openai≥1.82, pydantic, pandas, numpy, tenacity, pyaml |
| location | `external/AFlow/` (gitignored — not vendored into EvoPareto git) |

## License verdict

- Academic reproduction: **allowed**
- Modification: **allowed** (keep copyright notice)
- Redistribution: **allowed** with notice
- Datasets: separate (download via `data/download_data.py`; benchmark terms apply)

## Dependency lock

`requirements.txt` pins 23 packages. **Gap:** `scripts/utils/sanitize.py`
imports `tree_sitter`, which is **not** in requirements →
`DEPENDENCY_INCOMPATIBILITY` in offline env (pip blocked by proxy).
Smoke test stubs it for import only; no algorithm change.

```text
AFLOW_SOURCE_PINNED: YES
AFLOW_COMMIT: 3f457218fc716093fe53f6df8a5d5e6379d66346
LICENSE_VERIFIED: YES (MIT)
DEPENDENCY_LOCK_STATUS: PARTIAL (tree_sitter missing from requirements)
```
