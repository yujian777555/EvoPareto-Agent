# R3.5 Next Experiment Plan (offline — awaiting authorization)

## Arms (dev selection only; confirm never used for selection)

| Arm | Role |
|---|---|
| P | frozen Parent baseline |
| R | original random mutation (`OP_ERROR_RECOVERY` etc.) |
| F_old | R3.4-style `OP_ARITH_RECHECK` (historical mechanism control) |
| F_local | new append-only local suffix from real FeedbackDiagnosis |
| E2_local | from **pre-registered winner among {R, F_local}** using that winner's real FailureRecords |

## Tasksets (frozen R3.5)

* Dev **20** · SHA `5838ae12ac4b55019f1286ef79eed7509dd3893a3e180099e9db32a4e64a8890`
* Confirm **30** · SHA `8bafc69872c8583fd79556ba932da7aded988936bb193fcebd6d28416cd2ea42`
* R3.4 confirm tasks **diagnostic only** (not a new confirmation set)
* Train SHA `17f347dc…`; seed `20260605`; all historical indices excluded

## Hypotheses to discriminate (not pre-decided)

* H1 over-constrained verify prompts → F_local should not collapse vs P
* H2 coarse attribution → still limited to `ANSWER_MISMATCH`
* H3 destroyed solve logic → F_local preserves instruction prefix
* H4 seed noise → needs multi-seed follow-up (not this single run)

## Budget estimate (full 5-arm design)

| Block | Calls |
|---|---:|
| Dev P,R,F_old,F_local (20×4) | 80 |
| E2_local dev (20) | 20 |
| Confirm 30×5 arms | 150 |
| Retry / margin 10% | 25 |
| **Total** | **≈ 275** |

Worst-case tokens: in 275×1500, out 275×300 → 412k / 82k  
Worst-case cost ≈ 275 × $0.00081 ≈ **$0.23** (suggest cap **$0.30**)

### Reduced option (if limited)

Dev 20×4 + E2 20 + confirm 30×3 (P, winner, F_local) = 80+20+90 = **190**  
Margin 10% → **209** req · worst ≈ **$0.17** · cap **$0.20**

## Authorization status

**NOT AUTHORIZED.** R3.4 remaining 13 requests does **not** cover R3.5.  
Do not reset ledgers. Do not run partial live experiments.

## Ready-to-run checklist

- [x] Failure attribution from real R3.4 data  
- [x] F_LOCAL operator + lineage records + NO_OP / NO_USABLE_FEEDBACK  
- [x] Independent taskset freeze (20/30)  
- [x] Offline tests  
- [ ] Planner/user budget grant  
- [ ] Live run entry wiring (reuse `run_micro_r34` pattern)
