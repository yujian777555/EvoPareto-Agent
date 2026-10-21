# R3 Budget Estimate (conservative) — not an authorization

## Assumed design (if Planner approves)

| Block | Tasks | Arms | Calls/arm | Notes |
|---|---:|---|---:|---|
| Screening (optional) | 10 | P | 1 | error-rate discovery |
| Dev R vs F | 5 | R, F | 1 | 10 calls |
| Dev E2 | 5 | E2 | 1 | 5 calls |
| Confirm | 8 | P, winner, E2 | 1 | 24 calls |
| Confirm S probe | 3 | S | 2 | 6 calls |
| **Core total (no screening)** | | | | **45** |
| **With screening** | | | | **55** |

## Token / cost (peak estimates)

* Input ≤ 1500, output ≤ 300 per request (project peak prices ~$0.30 / $1.20 per 1M).  
* Worst-case ≈ $0.00081 / request.  
* **45 req ≈ $0.036** worst-case; **55 ≈ $0.045**.  
* Suggested envelope: **60 physical requests, $0.05** (matches prior micro scale) **or** 80 requests / $0.08 if screening included.

## Caps to request

| Resource | Suggested |
|---|---:|
| Physical HTTP | 60 (core) or 80 (with screening) |
| Cost USD | $0.05–$0.08 |
| Tokens in/out | 1500 / 300 per request |

**Not authorized this round.** Must be a new independent grant.


## Corrected request plan (R3.1)

| Block | Requests |
|---|---:|
| Parent dev (feedback source) | 5 |
| R + F dev | 10 |
| E2 dev | 5 |
| Confirm 8×3 | 24 |
| S probe 3×2 | 6 |
| **Baseline** | **50** |
| **+10% → suggested cap** | **55** |
