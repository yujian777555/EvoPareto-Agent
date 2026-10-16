# Intervention Credit Design

Record: `(failure_context, operator, parent_reward, child_reward, task_id)`.
Δ = R(child) − R(parent) under the **same** task instance (paired contrast).

Update (exponential decay, λ=0.4):

```
w ← λ + (1−λ)w_prev
s ← λ·Δ + (1−λ)s_prev
credit = s / w
```

## Causal honesty

- Δ is a **paired estimate**, not a randomized causal effect. Environment is
  deterministic given (genome, task); no full counterfactual randomization.
- Single-step Δ can be noisy; decay smooths but does not identify causality.
- Ground-truth fault type is excluded from the credit key.
- Comparison controls (shuffled evidence) test *dependence on failure info*,
  which is necessary but not sufficient for causal claims about mechanisms.
