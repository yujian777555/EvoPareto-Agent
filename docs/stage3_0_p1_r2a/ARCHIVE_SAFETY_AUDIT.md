# Archive Safety Audit (Task E)

**Evidence class:** MOCK_TEST (crafted malicious tars) + OFFICIAL_DATA (SHA-256)
**Script:** `scripts/baseline_first/run_safety_gates_v2.py`
**Result:** `results/stage3_0_p1_r2a/archive_negative_tests.json`

## Official archive

| Item | Value |
|---|---|
| path | `C:\Users\于舰\Downloads\results.tar.gz` |
| SHA-256 | `F460F9C9218216F6FBAF553F4F215248317B7F37DD715AE146CD38199EABE5F7` |
| members | 1720 |
| contains symlink | False |
| contains absolute path | False |
| contains traversal | False |

Official content was **not modified**. Extraction is per-member (no `extractall`).

## Protections

- absolute path / drive-letter / UNC reject
- `..` traversal reject
- symlink **and** hardlink reject
- special files (fifo/chr/blk) reject
- per-file size cap 50 MB, total 200 MB, 50k file cap
- final resolved path must stay under destination
- no overwrite of existing files

## Negative tests (all must be REJECTED)

{
  "traversal": "REJECTED:TRAVERSAL:../escape.txt",
  "absolute": "REJECTED:ABSOLUTE_PATH:/abs.txt",
  "windows_absolute": "REJECTED:ABSOLUTE_PATH:C:\\evil.txt",
  "symlink": "REJECTED:LINK:link",
  "hardlink": "REJECTED:LINK:hlink",
  "special_fifo": "REJECTED:SPECIAL_FILE:fifo",
  "overwrite": "REJECTED:OVERWRITE:a.txt",
  "file_too_big": "REJECTED:FILE_TOO_BIG:big.bin:53477376"
}

**all_rejected = True**
**verdict = ARCHIVE_SAFETY_PASS**
