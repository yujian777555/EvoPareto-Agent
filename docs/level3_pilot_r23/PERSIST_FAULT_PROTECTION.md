# Persistence Fault Protection (Task B)

## Fixes

1. **Marker write failure is no longer silent.** If both the record write and
   the `PERSIST_FAULT` marker write fail, the system raises
   `PROTECTION_NOT_PERSISTABLE` and records
   `NEITHER_RECORD_NOR_FAULT_MARKER_WRITABLE` — it does NOT pretend a
   cross-process latch was armed.
2. **Conditional skips removed** from core safety tests. If the cross-process
   block is not implemented the test FAILS, it does not skip.

## Two distinct guarantees

| Scenario | Guarantee |
|---|---|
| `os.replace` fails (record write) | fault marker lands → new process refuses to load |
| both record AND marker writes fail | **cannot** guarantee cross-process block; loud `PROTECTION_NOT_PERSISTABLE`; manual recovery required |

The second scenario cannot be solved by writing another marker to the same
failing filesystem. A fully independent external latch (e.g. a separate
device) would be required; that is recorded as a documented limitation, not
claimed as solved.

## Tests (5)

- `settle_actual` os.replace failure → marker → new instance refused
- marker write failure → `PROTECTION_NOT_PERSISTABLE` reported
- no `pytest.skip` in core safety tests
- actual usage evidence kept on settle failure
- unsettled reservations survive restart
