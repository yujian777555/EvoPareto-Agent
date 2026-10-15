# Phase5-R3-R5-R2 — HV Validity

`src/evaluation/hv_2d.py` exact mixed-direction 2D HV.

**Golden case:** A=(0.9,0.10), D=(0.5,0.05), ref=(0.0,0.20) → **HV = 0.115** ✅

Handles: dominated points, empty set, zero success, tiny cost, ref boundary.

Formal experiments must use a **fixed** pre-registered reference point
(e.g. `(0.0, 1.0)` for synthetic, or frozen cost scale for USD). Never
recompute ref per generation when comparing HV gains.
