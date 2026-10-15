# Phase5-R3-R5-R2 — PPEC End-to-End

`two_obj_pipeline` no longer replaces `loop.nsga3` after PPEC init.

`Preference2DController` supplies 2D directions; env selection uses them.

Verified: success_first vs cost_first directions differ; strength=0 uniform;
dim mismatch raises; dominated solutions cannot win on preference score alone
(dominance still applied in NSGA-III).

Cost scale for PSS: raw USD in [0,1] clip for satisfaction; **HV uses raw USD**
with pre-registered ref `cost=1.0` for synthetic landscapes. No silent
re-scaling of Pareto objectives.
