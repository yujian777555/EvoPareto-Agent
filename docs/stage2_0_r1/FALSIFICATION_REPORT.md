# Falsification Report

## H1 (failure information improves operator selection)

**NOT SUPPORTED** as *conditioning* benefit: fceol == global_aos ==
contextual_bandit (0.200). True evidence > shuffled/unknown-only (+0.02) —
evidence quality matters, but a *conditioned* policy is not better than
unconditioned UCB here.

## H2 (intervention credit vs fixed map)

**NOT SUPPORTED:** fixed_map ties fceol at 0.200.

## H3 (generalization to held-out)

Frozen transfer: same ceiling for all learned policies. Oracle shows headroom
(0.384) but no policy generalizes a better selection strategy in 3 steps.

## What is preserved

- Valid interpreter + fair controls + exact oracle.
- Negative results kept: no FCEOL advantage; success-rate floor; oracle gap.
- Shuffled/wrong-diagnosis slightly worse → evidence *content* has value, but
  not enough to beat global AOS.

## Conclusion

**`FCEOL_BENEFIT_NOT_ESTABLISHED`** in this controlled environment.
Do not proceed to real-agent pilot claiming FCEOL superiority.
