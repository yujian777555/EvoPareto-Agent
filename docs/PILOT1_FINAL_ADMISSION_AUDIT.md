# Pilot1 Final Admission Audit

**HEAD `575346d`** → this commit · 0 real API

## P0-A cost zero bypass

`estimate_cost` statuses: KNOWN / UNKNOWN_USAGE / UNKNOWN_RATE.  
Unknown never pretends zero-true; `backend_estimated_cost` shares frozen rate.

## P0-B native smoke

Docker `alfworld-local:tw` + volume `alfworld-data`:
- alfworld importable ✅
- reset/step on real TextWorld ✅
- actual game_id ∈ valid_train ✅
- `won` read from env (false under Mock LLM — honest) ✅
- 2D fitness from won + cost ✅
- `native_dry_run_status=PASS`

## P0-C manifest

Smoke records `manifest_sha256`; live entry still requires frozen manifest +
`--live`. Game identity persisted in episode JSON.
