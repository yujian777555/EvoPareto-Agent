# Persistence Failure Cross-Process Audit (Task C)

## Problem

`_persist()` failure set only the in-memory `_poisoned` flag. A restarted
process would `open_existing()` the still-valid disk record and continue.

## Fix

A durable **fault marker** is written next to the record on persist failure:

```
authorization_record.json.PERSIST_FAULT
```

`_reload()` refuses to load when the marker is present
(`AuthorizationIntegrityError: PERSIST_FAULT_MARKER_PRESENT`). This is a
cross-process fail-closed: a new process cannot silently continue.

## Tests (4)

1. persist-failure poisons the object AND the marker blocks a new instance
2. unsettled reservations and unknown-billing evidence are never zeroed
3. concurrent settle + reserve after over-limit: block is persisted
4. multiprocess restart keeps the consumed counter

## Note

The marker must be cleared by an **explicit manual recovery** procedure; the
system never auto-creates a new authorization to bypass it.
