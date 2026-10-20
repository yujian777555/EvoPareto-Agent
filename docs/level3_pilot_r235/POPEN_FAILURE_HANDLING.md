# Popen Failure Upper Handling (Task A)

When `_run_bounded()` returns `proc=None` or `popen_failed=True`:

1. `run_workflow_code_isolated()` immediately returns a structured failure:
   `ok=False`, `error=POPEN_FAILED`, `answer_text=None`, `docker_cleanup`.
2. `proc.returncode` is never accessed (previously caused `AttributeError`).
3. IPC server is stopped in `finally`; temp dirs cleaned.
4. Cleanup status reflects reality; cleanup failure is never reported as success.

Also added: `except Exception` around `_run_bounded` returns
`RUN_BOUNDED_EXCEPTION` as a structured failure instead of propagating.
