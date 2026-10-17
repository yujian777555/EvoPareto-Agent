# Cross-Process Atomic Budget Reservation (Task C)

## P0

`AuthorizationRecord.update()` held only a `threading.RLock`. Each Run ID used
its own SQLite working DB, so `BEGIN INNEDIATE` could not give global budget
atomicity across processes.

## Fix

1. **OS file lock** (`msvcrt.locking` on Windows, `fcntl.flock` on Unix) on
   `authorization_record.json.lock`, held across every `mutate()`.
2. Inside the lock the record is **re-read from disk** before mutation — a
   stale in-process `_body` is never written over a newer record.
3. Persist is `write-temp + fsync + os.replace`.
4. Working DB (deletable) and the trusted record stay consistent: the record
   is updated after the DB commit, so a crash leaves the record at least as
   conservative as the DB (an unused reservation or an outstanding reservation
   — both safe). A missing record entry is never read as zero consumption.

## Crash-window analysis

| crash point | outcome | safe? |
|---|---|---|
| after DB insert, before record update | DB shows RESERVED, record shows no spend | reservation unused (conservative) |
| after record update | both consistent | yes |
| during record persist (temp file) | os.replace is atomic; old record retained | yes |
| record missing after crash | open_existing fails closed | yes |
