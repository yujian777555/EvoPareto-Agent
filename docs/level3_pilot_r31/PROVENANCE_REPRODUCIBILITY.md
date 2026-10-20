# Provenance Audit Reproducibility (R3.1-R1)

Run the offline audit with:

```bash
python scripts/level3_pilot_r31/audit_gsm8k_provenance.py
```

The audit verifies the bundled official GSM8K test file before comparing tasks:

- SHA-256: `3730d312f6e3440559ace48831e51066acaca737f6eabec99bccb9e4b3c39d14`
- record count: 1,319
- R3 confirmation task count: exactly 35

## Matching rules

1. Normalize question text by collapsing whitespace runs to one space; all
   other text must match exactly.
2. Extract the official gold answer from text after the last `####` marker.
3. Normalize whitespace in the extracted and declared gold answers, then require
   an exact match.
4. A matching question without an extractable gold answer is
   `GOLD_UNVERIFIED`, never `OFFICIAL_MATCH`.
5. The output count categories must sum to all 35 audited tasks.

The pure `audit_provenance()` function reads source inputs and returns a report
without writing files by default. The CLI writes only the derived
`results/level3_pilot_r31/dataset_provenance_audit.json` artifact. It does not
modify the original R3 task set, original experiment outputs, or authorization
ledger.

The current evidence remains 0/35 matches on both question and gold answer.
These tasks must remain labelled synthetic/unmatched; no official GSM8K
generalization claim is supported.
