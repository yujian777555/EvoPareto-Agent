"""Unified 2D hypervolume used by evolution history (Phase R2-R1 Task C)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from src.evaluation.hv_2d import hypervolume_2d_mixed, reference_point_default


def hv_for_objectives(
    rows: Sequence[Sequence[float]],
    *,
    objective_version: str,
    ref: Optional[Sequence[float]] = None,
    hv_n_samples: int = 512,
    seed: int = 0,
) -> float:
    """Single entrypoint for HV in evolution stats.

    candidate_2obj -> exact mixed 2D HV with fixed ref
    legacy_5obj   -> legacy hypervolume (unchanged)
    """
    if objective_version == "candidate_2obj":
        r = list(ref) if ref is not None else list(reference_point_default(1.0))
        return hypervolume_2d_mixed(rows, r)
    # legacy path
    from src.evaluation.metrics import hypervolume

    return hypervolume(rows, n_samples=hv_n_samples, seed=seed)


def default_2d_ref() -> Tuple[float, float]:
    return reference_point_default(1.0)
