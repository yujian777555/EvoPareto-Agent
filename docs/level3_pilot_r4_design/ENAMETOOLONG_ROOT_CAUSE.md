# ENAMETOOLONG Root-Cause Note (R4-R4)

## Symptom

Prior session tool log ended with:

```
spawn ENAMETOOLONG
```

## Root cause (identified)

| Item | Finding |
|---|---|
| Failing operation | A single `bash` tool invocation that inlined a **very large** Python source as a `python -c` / heredoc payload |
| Command shape | `python - <<'PY' ... ~15KB of source ... PY` or `python -c "<multi-KB script>"` passed as one OS command line |
| Why it failed | Windows process spawn / argv length limit exceeded (`ENAMETOOLONG`); PowerShell also does not support `<<'PY'` heredocs, producing follow-on parse errors |
| Category | **tool-call command construction**, not pytest, not git, not the code under test |
| Occurrence | While concatenating `r4_workflow_program.py` parts and while patching large test files |

## Fix (applied this round)

1. Never inline large scripts in the shell command line.
2. Always write scripts with the `write` tool to `scripts/_tmp_*.py`, then `python scripts\_tmp_*.py`.
3. Split large module edits into several smaller write/patch scripts.
4. Avoid `python - <<'PY'` under PowerShell entirely.

## Verification this round

| Check | Result |
|---|---|
| Large module assembled via multiple `write` + file concat | **OK** (no ENAMETOOLONG) |
| Seed audit / freeze / doc patches via file scripts | **OK** |
| Pytest full/targeted runs via `scripts/_tmp_run_*.py` | **OK** (see delivery log) |
| Git commit/push | **OK** (short argv) |

## Residual uncertainty

Cannot replay the exact historical argv byte length (shell history not preserved).  
Evidence: the failure coincided only with oversized inlined source commands; all file-mediated commands in this round succeeded.  
**Not ignored** — construction rule above is now the standing practice.
