# Bounded Output Capture (Task C)

`_run_bounded()` caps stdout/stderr at 4 MB each with threaded drains; overflow
kills the process and returns `PIPE_OVERFLOW` with `answer_text=None`.
Overflow refuses scoring. Docker + IPC cleaned up in `finally`.
6 regression tests. Host-memory protection documented; line-rate writers are
stopped by the cap.
