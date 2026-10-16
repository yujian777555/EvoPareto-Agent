# FCEOL Method

`src/research/fceol/operator_policy.py` + `intervention_credit.py`.

## Decision

```
m_t ~ π(m | f_t, g_t, D_t)
```

FCEOL = UCB over operators **conditioned on** `evidence.context_key()`:

```
score(m) = credit_mean(ctx, m) + c·sqrt(log t_ctx / n_ctx(m))
```

- Untried operators are tried first (exploration).
- `ctx:UNKNOWN` uses larger `c` (more exploration).
- Credit = decayed mean of paired Δ=R(child)−R(parent).

## Honest framing

This is a **contextual-bandit operator policy**. The research content is in
(i) failure-evidence representation with UNKNOWN handling, (ii) paired
intervention credit, (iii) controls that test whether failure information
actually matters (shuffled labels). Not a new bandit algorithm.

## Baselines

random · global_aos (UCB, no context) · fixed_map (heuristic) ·
fceol · shuffled (wrong context) · oracle (isolated ceiling; implementation
caveat: current oracle repeats one op and underperforms — do not treat its
score as a true upper bound).
