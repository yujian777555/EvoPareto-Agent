# Atomic Reservation & Settlement State Machine (Task C)

## States

```
RESERVED
   ├──► SETTLED_ACTUAL              (trusted usage known)
   └──► SETTLED_UNKNOWN_BLOCKED     (usage unverifiable -> persistent block)
```

- `physical_request_id` is `UNIQUE` in the working DB — duplicates rejected.
- Only `RESERVED` can transition; any other source state raises
  `DuplicateSettlement`. There is no repair-to-success path.
- A settlement failure rolls back the SQLite transaction and does **not**
  release the reservation in the trusted record.
- `SETTLED_UNKNOWN_BLOCKED` keeps the reservation as consumed (conservative)
  and sets `blocked=true` so every later reserve fails.

## Verified inequalities

- outstanding reservations jointly counted toward the cost cap
- physical cap enforced after mixed settlements
- cumulative output-token cap enforced
- 8-thread concurrent reservations never exceed the cost cap
