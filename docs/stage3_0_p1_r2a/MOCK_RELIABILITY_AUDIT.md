# Mock Reliability Audit

Fresh run_id = `c91d8c584a76` · exit_code = 0 ·
search_loop = PASS.

`run_safety_gates.py` returns **non-zero** if any gate fails (verified).
Each mock run uses a unique run_id; results are per-run artifacts. Negative
tests (format/save failures) exercised via crafted archives and budget
exhaustion. Mock ≠ real model success.
