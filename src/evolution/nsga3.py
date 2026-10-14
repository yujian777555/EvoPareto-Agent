"""NSGA-III: non-dominated sorting + reference directions + niching selection.

Implemented from scratch (Deb & Jain 2014) for many-objective agent
configuration search. Supports >= 5 objectives.

Internal convention
-------------------
All comparisons are **minimization**. Callers pass already-signed objective
vectors (see `src/evaluation/objectives.py`).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from src.agent.individual import Individual


# ====================================================================== #
# Reference directions (Das & Dennis simplex-lattice)
# ====================================================================== #
def generate_reference_directions(
    n_objectives: int, divisions: int
) -> List[List[float]]:
    """Uniform reference directions on the unit simplex.

    Uses the Das-Dennis lattice: number of points = C(divisions + M - 1, M - 1).
    """
    if n_objectives < 2:
        raise ValueError("n_objectives must be >= 2")
    if divisions < 1:
        raise ValueError("divisions must be >= 1")

    directions: List[List[float]] = []

    def recurse(remaining: int, dims_left: int, prefix: List[int]) -> None:
        if dims_left == 1:
            directions.append([x / divisions for x in prefix + [remaining]])
            return
        for i in range(remaining + 1):
            recurse(remaining - i, dims_left - 1, prefix + [i])

    recurse(divisions, n_objectives, [])
    return directions


# ====================================================================== #
# Dominance
# ====================================================================== #
def dominates(a: Sequence[float], b: Sequence[float]) -> bool:
    """True if a Pareto-dominates b under minimization."""
    strictly_better = False
    for x, y in zip(a, b):
        if x > y:
            return False
        if x < y:
            strictly_better = True
    return strictly_better


def non_dominated_sort(
    fitness_rows: Sequence[Sequence[float]],
) -> List[List[int]]:
    """Fast non-dominated sort. Returns fronts as index lists (rank 0 = best)."""
    n = len(fitness_rows)
    if n == 0:
        return []

    S: List[List[int]] = [[] for _ in range(n)]
    n_dom = [0] * n
    rank = [0] * n
    fronts: List[List[int]] = [[]]

    for p in range(n):
        for q in range(n):
            if p == q:
                continue
            if dominates(fitness_rows[p], fitness_rows[q]):
                S[p].append(q)
            elif dominates(fitness_rows[q], fitness_rows[p]):
                n_dom[p] += 1
        if n_dom[p] == 0:
            rank[p] = 0
            fronts[0].append(p)

    i = 0
    while fronts[i]:
        next_front: List[int] = []
        for p in fronts[i]:
            for q in S[p]:
                n_dom[q] -= 1
                if n_dom[q] == 0:
                    rank[q] = i + 1
                    next_front.append(q)
        i += 1
        fronts.append(next_front)

    # Drop trailing empty front if present.
    if fronts and not fronts[-1]:
        fronts.pop()
    return fronts


def pareto_front_indices(
    fitness_rows: Sequence[Sequence[float]],
) -> List[int]:
    """Indices of the non-dominated set (front 0)."""
    fronts = non_dominated_sort(fitness_rows)
    return list(fronts[0]) if fronts else []


# ====================================================================== #
# Normalization + association + niching
# ====================================================================== #
def _ideal_point(fitness_rows: Sequence[Sequence[float]]) -> List[float]:
    m = len(fitness_rows[0])
    return [min(row[j] for row in fitness_rows) for j in range(m)]


def _nadir_from_extreme(
    fitness_rows: Sequence[Sequence[float]],
    ideal: Sequence[float],
    front_indices: Sequence[int],
) -> List[float]:
    """Approximate nadir using intercepts / axis intercepts of first front.

    Falls back to max over provided rows if intercepts are degenerate.
    """
    m = len(ideal)
    if not front_indices:
        return [max(row[j] for row in fitness_rows) for j in range(m)]

    # Extreme points: for each objective axis, the point on the front that
    # minimizes the achievement scalarizing function with a weight vector
    # putting almost all weight on that axis.
    eps = 1e-10
    extreme: List[int] = []
    for j in range(m):
        weights = [eps] * m
        weights[j] = 1.0
        best_idx = front_indices[0]
        best_val = math.inf
        for idx in front_indices:
            # ASF = max_i (f_i - z_i) / w_i
            asf = 0.0
            for k in range(m):
                val = (fitness_rows[idx][k] - ideal[k]) / max(weights[k], eps)
                if val > asf:
                    asf = val
            if asf < best_val:
                best_val = asf
                best_idx = idx
        extreme.append(best_idx)

    # Build hyper-plane through extreme points via least squares.
    # Solve A w = 1, then intercepts = ideal + 1/w.
    # Use normal equations with simple Gaussian elimination (m is small).
    matrix = [[fitness_rows[idx][k] - ideal[k] for k in range(m)] for idx in extreme]
    # Try to solve matrix @ w = ones
    ones = [1.0] * m
    w = _solve_linear(matrix, ones)
    if w is not None:
        intercepts = []
        ok = True
        for k in range(m):
            if abs(w[k]) < 1e-12:
                ok = False
                break
            intercepts.append(ideal[k] + 1.0 / w[k])
        if ok and all(math.isfinite(x) for x in intercepts):
            # Ensure nadir is at least the front max (numerical safety).
            front_max = [max(fitness_rows[i][k] for i in front_indices) for k in range(m)]
            return [max(intercepts[k], front_max[k]) for k in range(m)]

    # Fallback: component-wise max over first front (or all rows).
    src = [fitness_rows[i] for i in front_indices] or list(fitness_rows)
    return [max(row[k] for row in src) for k in range(m)]


def _solve_linear(
    matrix: List[List[float]], rhs: List[float]
) -> Optional[List[float]]:
    """Gaussian elimination for a small dense system. Returns None if singular."""
    m = len(matrix)
    a = [list(matrix[i]) + [float(rhs[i])] for i in range(m)]
    for col in range(m):
        pivot = max(range(col, m), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-14:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        for j in range(col, m + 1):
            a[col][j] /= div
        for r in range(m):
            if r == col:
                continue
            factor = a[r][col]
            if factor == 0:
                continue
            for j in range(col, m + 1):
                a[r][j] -= factor * a[col][j]
    return [a[i][m] for i in range(m)]


def normalize_fitness(
    fitness_rows: Sequence[Sequence[float]],
    front_indices: Sequence[int],
) -> Tuple[List[List[float]], List[float], List[float]]:
    """Translate by ideal point and scale by intercept ranges.

    Returns (normalized_rows, ideal, extreme_range).
    """
    if not fitness_rows:
        return [], [], []
    ideal = _ideal_point(fitness_rows)
    intercepts = _nadir_from_extreme(fitness_rows, ideal, front_indices)
    ranges = [
        max(intercepts[j] - ideal[j], 1e-12) for j in range(len(ideal))
    ]
    normalized = [
        [(row[j] - ideal[j]) / ranges[j] for j in range(len(ideal))]
        for row in fitness_rows
    ]
    return normalized, ideal, ranges


def associate_to_references(
    normalized_rows: Sequence[Sequence[float]],
    directions: Sequence[Sequence[float]],
    indices: Sequence[int],
) -> Tuple[Dict[int, int], Dict[int, float]]:
    """Map each index to nearest reference line (perpendicular distance)."""
    assoc: Dict[int, int] = {}
    dist: Dict[int, float] = {}
    for idx in indices:
        row = normalized_rows[idx]
        best_d = math.inf
        best_r = 0
        for r, w in enumerate(directions):
            d = _perpendicular_distance(row, w)
            if d < best_d:
                best_d = d
                best_r = r
        assoc[idx] = best_r
        dist[idx] = best_d
    return assoc, dist


def _perpendicular_distance(
    point: Sequence[float], direction: Sequence[float]
) -> float:
    """Distance from point to the line spanned by `direction` (from origin)."""
    # project: t = <p,w>/<w,w>; residual = p - t w
    ww = sum(x * x for x in direction)
    if ww < 1e-18:
        return math.sqrt(sum(x * x for x in point))
    t = sum(p * w for p, w in zip(point, direction)) / ww
    residual = [p - t * w for p, w in zip(point, direction)]
    return math.sqrt(sum(x * x for x in residual))


# ====================================================================== #
# Niching selection for the critical front
# ====================================================================== #
def niching_select(
    normalized_rows: Sequence[Sequence[float]],
    directions: Sequence[Sequence[float]],
    last_front: Sequence[int],
    n_select: int,
    niche_counts: Dict[int, int],
) -> List[int]:
    """Select `n_select` members from `last_front` using reference niching."""
    assoc, dist = associate_to_references(normalized_rows, directions, last_front)

    # Group front members by reference index.
    ref_to_members: Dict[int, List[int]] = {r: [] for r in range(len(directions))}
    for idx in last_front:
        ref_to_members[assoc[idx]].append(idx)

    # Sort each niche by distance to its reference line (prefer closer).
    for r in ref_to_members:
        ref_to_members[r].sort(key=lambda i: dist[i])

    selected: List[int] = []
    selected_set = set()
    remaining = list(last_front)

    while len(selected) < n_select:
        # Reference with minimum niche count among those with available members.
        candidates = [
            r
            for r in range(len(directions))
            if ref_to_members[r]
        ]
        if not candidates:
            # Fallback: pick any remaining.
            for idx in remaining:
                if idx not in selected_set and len(selected) < n_select:
                    selected.append(idx)
                    selected_set.add(idx)
            break

        min_count = min(niche_counts.get(r, 0) for r in candidates)
        min_refs = [r for r in candidates if niche_counts.get(r, 0) == min_count]

        if len(min_refs) == 1:
            chosen_ref = min_refs[0]
            member = ref_to_members[chosen_ref].pop(0)
            selected.append(member)
            selected_set.add(member)
            niche_counts[chosen_ref] = niche_counts.get(chosen_ref, 0) + 1
        else:
            # Tie-breaking: randomly pick among min-count refs (Jain rule).
            rng = random.Random(0)  # deterministic per call site via outer seed
            # Use non-deterministic global RNG for true diversity:
            chosen_ref = random.choice(min_refs)
            members = ref_to_members[chosen_ref]
            if members:
                member = members.pop(0)
            else:
                # Should not happen; skip.
                continue
            if member not in selected_set:
                selected.append(member)
                selected_set.add(member)
                niche_counts[chosen_ref] = niche_counts.get(chosen_ref, 0) + 1

    return selected


# ====================================================================== #
# Main NSGA-III environmental selection
# ====================================================================== #
@dataclass
class NSGA3Config:
    n_objectives: int = 5
    divisions: int = 3  # Das-Dennis H
    seed: Optional[int] = 42


class NSGA3:
    """Environmental selection of a parent+offspring pool to size `pop_size`."""

    def __init__(
        self,
        n_objectives: int = 5,
        divisions: int = 3,
        seed: Optional[int] = 42,
    ) -> None:
        self.config = NSGA3Config(n_objectives, divisions, seed)
        if seed is not None:
            random.seed(seed)
        self.directions = generate_reference_directions(n_objectives, divisions)

    # public helpers -------------------------------------------------- #
    def reference_directions(self) -> List[List[float]]:
        return [list(d) for d in self.directions]

    def select(
        self,
        population: List[Individual],
        pop_size: int,
    ) -> List[Individual]:
        """Return `pop_size` individuals chosen from `population` by NSGA-III."""
        if pop_size <= 0:
            raise ValueError("pop_size must be positive")
        if not population:
            return []
        if len(population) <= pop_size:
            return list(population)

        for ind in population:
            if not ind.has_fitness():
                raise ValueError("all individuals must have fitness_vector set")

        fitness_rows = [list(ind.fitness_vector or []) for ind in population]
        fronts = non_dominated_sort(fitness_rows)

        selected_idx: List[int] = []
        for front in fronts:
            if len(selected_idx) + len(front) <= pop_size:
                selected_idx.extend(front)
            else:
                n_needed = pop_size - len(selected_idx)
                normalized, _, _ = normalize_fitness(fitness_rows, fronts[0])
                niche_counts: Dict[int, int] = {r: 0 for r in range(len(self.directions))}
                # Seed niche counts from already accepted members.
                accepted_assoc, _ = associate_to_references(
                    normalized, self.directions, selected_idx
                )
                for idx in selected_idx:
                    r = accepted_assoc[idx]
                    niche_counts[r] = niche_counts.get(r, 0) + 1

                picked = niching_select(
                    normalized,
                    self.directions,
                    front,
                    n_needed,
                    niche_counts,
                )
                selected_idx.extend(picked[:n_needed])
                break

        return [population[i] for i in selected_idx]

    def sort_fronts(self, population: List[Individual]) -> List[List[int]]:
        fitness_rows = [list(ind.fitness_vector or []) for ind in population]
        return non_dominated_sort(fitness_rows)

    def pareto_front(self, population: List[Individual]) -> List[Individual]:
        fronts = self.sort_fronts(population)
        if not fronts:
            return []
        return [population[i] for i in fronts[0]]
