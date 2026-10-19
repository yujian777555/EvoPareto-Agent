# Child Graph SHA Mandatory (Task 2)

`child_graph_sha256` in the re-verification file is now a **required** field:
- missing → `REVERIFICATION_CHILD_SHA_MISSING`, exit 2
- wrong value → `REVERIFICATION_CHILD_SHA_MISMATCH`, exit 2
- valid → rescore reproduces frozen 11/12 ↔ 11/12, net gain 0

Integrity manifest is never reset to mask data changes.
3 regression tests: delete field / wrong hash / valid reproduction.
