# Provenance Audit Reproducibility (Task C)

`scripts/level3_pilot_r31/audit_gsm8k_provenance.py` is a standalone offline
script that reproduces the 0/35 match finding.

## Verification chain

1. Official file SHA-256 == `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`
2. Official record count == 1319
3. All 35 R3 questions matched by normalized text (whitespace collapse)
4. Gold extraction: text after last `####` in official answer
5. Output counts verified: 0 official, 35 synthetic/unmatched

## Normalization rules

- Text: collapse all whitespace runs to single spaces, exact match
- Gold: extract after last `####` marker; if absent, no gold extracted
- Unmatched → `SYNTHETIC_OR_UNMATCHED` (never silently promoted to official)

The audit **never modifies** R3 task sets, results, or ledgers.
