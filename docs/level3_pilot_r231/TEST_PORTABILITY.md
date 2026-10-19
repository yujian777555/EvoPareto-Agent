# Test Path Portability (Task B)

Hardcoded `D:/` path replaced with ROOT-relative. The
`FileSystem.makeDirectory (C:\Users\한舰\...)` error came from this session's
write-tool path typos (Korean 한舰 vs Chinese 于舰), not from the test suite.
Tests use `tempfile`/`pathlib` only.
