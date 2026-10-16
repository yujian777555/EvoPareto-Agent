# Failure Identifiability Review (Candidate A)

## Question

Can the search algorithm tell *what to fix next* from the failure trace?

## Evidence from literature

- **2610.14662** ("Does Failure Feedback Direct Agent Self-Modification?")
  directly tests this: 145 DGM modifications show **no detectable
  target-specific repair advantage**; target feedback helps only in
  identifiable/repairable settings.
- **EnactOpt (2610.14977)** diagnoses "evidence missing vs evidence unused" —
  already operationalizes part of identifiability.
- **CoCoEvolve (2610.12794)** probes the live system before proposing edits.

## Our FCEOL lesson

Same symptom ≠ same root cause; policies could not exploit conditioning
(FCEOL = contextual bandit). This *confirms* the identifiability problem but
does **not** give us a publishable mechanism.

## Gap status

The observational question is **already answered** by 2610.14662. A mechanism
that *chooses DIAGNOSE vs MUTATE* using identifiability estimates is only a
thin gap and is adjacent to active diagnosis / Bayesian experimental design
(classic). **HIGH_COLLISION_RISK** for a paper framed solely on this.
