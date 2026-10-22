# R354_R12 Data Provenance Handoff

## Verified facts

| Item | Value |
|---|---|
| Branch | planner/r354-r11-runtime-gates |
| Baseline | 9734250d46f902fda0a81de1533de532f40e9eaf |
| File | results/level3_pilot_r4_data/gsm8k_train_official.jsonl |
| Bytes | 4,166,206 |
| Lines | 7,473 |
| Encoding | UTF-8, no BOM, LF line endings |
| SHA-256 (LF bytes on disk) | 17f347dc51477c50d4efb83959dbb7c56297aba886e5544ee2aaed3024813465 |
| SHA-256 (CRLF-converted bytes) | 232fb47faf81ea8b426cd2e5210c1dcad1a393ec8c0047ba6be9ef3a0e5f726b |
| Manifest train_sha256 | 17f347dc… (matches LF disk bytes) |
| Frozen tasks content match | 55/55 exact (question + gold vs current train) |

## Root cause (inference, high confidence)

The reported 232fb47f hash is the **same records** with CRLF newlines (Windows
checkout / autocrlf), not a different GSM8K version. LF→CRLF of this file
reproduces 232fb47f exactly. Record semantics and indices are identical.

**Not a data-version mismatch. Not a file replacement. Manifest is correct
for the canonical LF form.**

## Repair chosen: Plan 2-lite (no manifest rewrite)

* Manifest **unchanged** (it already declares the correct LF SHA).  
* Add .gitattributes rule 
esults/level3_pilot_r4_data/*.jsonl text eol=lf so
  checkouts cannot silently flip to CRLF.  
* Document both SHAs so future audits do not treat line-ending drift as
  source fraud.

## Pre-existing 3 test failures

Root cause = newline drift in the test environment, not wrong data:

| Test | Baseline (CRLF env) | This branch (LF) |
|---|---|---|
| test_preflight_tamper_zero_http | FAIL | PASS |
| test_preflight_index_mapping | FAIL | PASS |
| test_preflight_detects_hash_tamper | FAIL | PASS |

Recomputed SHA on LF bytes matches manifest; tests expect 17f347dc.

## Status

* Historical R3.5.3+ results **unmodified**.  
* Frozen task sets **not rebuilt**.  
* Real HTTP: **0**.  
* R3.5.4 mechanism hypothesis **not** validated by this work.

## Planner decisions needed

1. Accept LF as canonical provenance form (recommended).  
2. Optionally add a content-level (newline-insensitive) SHA alongside byte SHA.  
3. Then authorize R3.5.4 real run (still pending).
