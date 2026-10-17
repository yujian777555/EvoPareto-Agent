# Token Limits & Atomic Cost Reservation (Task C)

## Fix

`pre_send_ticket(..., res_cost=reserve_cost)` now forwards the **worst-case
peak cache-miss cost for this request's token bounds** into the SQLite atomic
reservation. The flat `est_cost_per_request=0.0005` default is no longer used
when a real reserve is supplied.

Reservation covers:
- input = conservative upper bound for THIS prompt (`len(prompt)+8`)
- output = full per-request output cap
- cost = `worst_case_cost(model, est_in, max_out)` at peak cache-miss rates

## Regression tests

`tests/baseline_first/test_reservation.py`:
- `test_reservation_is_worst_case_not_flat_default`
- `test_low_budget_rejects_expensive_request` (refused BEFORE send)
- `test_reserve_cost_matches_peak_formula`

## Optimizer prompt length distribution

{
  "run_id": "6a6b2052dac7",
  "n": 2,
  "max": 6049,
  "mean": 3109.5,
  "samples_top20": [
    6049,
    170
  ],
  "note": "conservative_input_tokens=len(prompt)+8 upper bound"
}

Measured with `conservative_input_tokens` (upper bound, not an exact tokenizer).

## Token limit proposal (requires Planner approval)

{
  "evidence_class": "DERIVED_STATISTICS",
  "current_max_input_per_request": 2000,
  "current_max_output_per_request": 500,
  "observed_max_prompt_len": 6049,
  "observed_mean_prompt_len": 3109.5,
  "measurement_note": "conservative_input_tokens = len(prompt)+8, an upper bound not an exact tokenizer count. AFlow optimizer prompts are experience+graph+instruction composites and run longer than 2000 tokens.",
  "proposed_max_input_per_request": 8000,
  "proposed_max_output_per_request": 500,
  "proposal_rationale": "Raise MAX_INPUT_TOKENS_PER_REQUEST to 8000 so official AFlow optimizer prompts can be sent without truncation. Output stays 500 (structured XML mutation fits comfortably).",
  "silent_truncation_used": false,
  "pilot_authorization_unchanged": true,
  "recomputed_worst_case_cost_per_request_usd": 0.003,
  "recomputed_worst_case_300_requests_usd": 0.9,
  "hard_cost_cap_usd": 5.0,
  "worst_case_cost_under_5usd": true,
  "output_token_sufficiency": "500 output tokens is sufficient for the AFlow XML mutation shape (<modification>/<graph>/<prompt>); no silent truncation of candidates.",
  "requires_planner_approval": true
}

**pilot_authorization_unchanged = True**
— this is a proposal only; the frozen $5 / 300-request / 2M-200k pilot is not
silently modified. No candidate is truncated to fit a limit.

Worst-case under the proposed 8000/500 bound:
**$0.003/request,
$0.9 for 300 requests**
(hard cap $5.00 stays safe).
