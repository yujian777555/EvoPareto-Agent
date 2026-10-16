# Offline Results

Real run: `python scripts/fceol/run_offline_experiment.py` (seed 42).  
Data: `results/stage2_0/{operator_policy_results,heldout_results,test_summary}.json`.

## Held-out (primary)

| Policy | mean Δ | success_rate | negative_rate |
|---|---:|---:|---:|
| **fceol** | **+0.142** | 0.688 | low |
| random | +0.094 | 0.625 | — |
| fixed_map | +0.085 | 0.688 | — |
| shuffled | −0.009 | 0.312 | — |
| global_aos | −0.017 | 0.813 | — |
| oracle* | −0.086 | 0.688 | — |

\*oracle implementation repeats one operator; ceiling unreliable.

## Train (secondary)

fceol mean Δ +0.007, success 0.889 (highest). global_aos success 0.833.

## Key contrasts (held-out mean Δ)

- fceol − global_aos = **+0.159**
- fceol − shuffled = **+0.151**
- fceol − random = **+0.048**

## Interpretation

- **Failure-conditioned selection improves intervention quality** (higher Δ)
  on unseen fault instances vs global AOS and vs shuffled labels.
- **Shuffled control collapses** (success 0.31, Δ≤0) → failure evidence
  carries real signal.
- **Success rate is mixed:** global_aos 0.81 > fceol 0.69 on held-out —
  FCEOL finds *better* mutations but not always more task successes within
  2 steps/task. Not a clean dominance.
- Train→heldout: fceol Δ actually higher on heldout (+0.14 vs +0.007) —
  positive transfer, small n.

## Limits

Synthetic env · small sample (40 held-out tasks × 2 steps) · oracle broken ·
no real LLM. **Not** proof for real agent harnesses.
