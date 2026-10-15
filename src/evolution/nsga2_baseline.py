"""NSGA-II baseline (Phase 5-Benchmark Extension).

Standard NSGA-II: non-dominated sorting + crowding distance + binary tournament.
**Baseline only** — NSGA-III core in `src/evolution/nsga3.py` is untouched.

Fitness convention matches PEEM-PPEC: paper semantics (mixed max/min);
internally converted to minimization for ranking.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from src.agent.individual import Individual
from src.evaluation.objectives import to_minimization
from src.evolution.nsga3 import non_dominated_sort


def crowding_distance(
    rows: Sequence[Sequence[float]],
    *,
    maximize_input: bool = True,
) -> List[float]:
    """NSGA-II crowding distance (larger = more isolated / preferred)."""
    n = len(rows)
    if n == 0:
        return []
    if n <= 2:
        return [math.inf] * n
    min_rows = [to_minimization(r) for r in rows] if maximize_input else [list(map(float, r)) for r in rows]
    m = len(min_rows[0])
    dist = [0.0] * n
    for j in range(m):
        order = sorted(range(n), key=lambda i: min_rows[i][j])
        dist[order[0]] = math.inf
        dist[order[-1]] = math.inf
        fmin = min_rows[order[0]][j]
        fmax = min_rows[order[-1]][j]
        span = fmax - fmin
        if span <= 1e-12:
            continue
        for k in range(1, n - 1):
            i = order[k]
            if math.isinf(dist[i]):
                continue
            dist[i] += (min_rows[order[k + 1]][j] - min_rows[order[k - 1]][j]) / span
    return dist


def binary_tournament(
    rng: random.Random,
    idx_a: int,
    idx_b: int,
    ranks: Sequence[int],
    crowding: Sequence[float],
) -> int:
    """Pick the better of two indices: lower rank, then higher crowding."""
    if ranks[idx_a] != ranks[idx_b]:
        return idx_a if ranks[idx_a] < ranks[idx_b] else idx_b
    if crowding[idx_a] != crowding[idx_b]:
        return idx_a if crowding[idx_a] > crowding[idx_b] else idx_b
    return idx_a if rng.random() < 0.5 else idx_b


@dataclass
class NSGA2Config:
    n_objectives: int = 5
    seed: Optional[int] = 42


class NSGA2:
    """NSGA-II environmental / mating selection (baseline)."""

    def __init__(self, n_objectives: int = 5, seed: Optional[int] = 42) -> None:
        self.config = NSGA2Config(n_objectives, seed)
        if seed is not None:
            self.rng = random.Random(seed)
        else:
            self.rng = random.Random()

    def _min_rows(self, population: Sequence[Individual]) -> List[List[float]]:
        from src.evaluation.objective_spec import SPEC_2, SPEC_5

        rows = [list(i.fitness_vector or []) for i in population]
        if rows and len(rows[0]) == 2:
            spec = SPEC_2
        else:
            spec = SPEC_5
        return [spec.to_minimization(r) for r in rows]

    def ranks_and_crowding(
        self, population: Sequence[Individual]
    ) -> Tuple[Dict[int, int], Dict[int, float]]:
        rows = self._min_rows(population)
        fronts = non_dominated_sort(rows)
        ranks: Dict[int, int] = {}
        crowding: Dict[int, float] = {}
        for fi, front in enumerate(fronts):
            front_rows = [rows[i] for i in front]
            cd = crowding_distance(front_rows, maximize_input=False)
            for k, idx in enumerate(front):
                ranks[population[idx].individual_id] = fi
                crowding[population[idx].individual_id] = cd[k]
        return ranks, crowding

    def select(self, population: List[Individual], pop_size: int) -> List[Individual]:
        """NSGA-II environmental selection (μ+λ style truncate)."""
        if pop_size <= 0:
            raise ValueError("pop_size must be positive")
        if not population:
            return []
        if len(population) <= pop_size:
            return list(population)

        rows = self._min_rows(population)
        fronts = non_dominated_sort(rows)
        chosen: List[int] = []
        for front in fronts:
            if len(chosen) + len(front) <= pop_size:
                chosen.extend(front)
            else:
                n_needed = pop_size - len(chosen)
                front_rows = [rows[i] for i in front]
                cd = crowding_distance(front_rows, maximize_input=False)
                order = sorted(range(len(front)), key=lambda k: -cd[k])
                chosen.extend(front[order[k]] for k in range(n_needed))
                break
        return [population[i] for i in chosen]

    def tournament_select(
        self,
        population: Sequence[Individual],
        *,
        n_select: int,
        ranks: Optional[Dict[int, int]] = None,
        crowding: Optional[Dict[int, float]] = None,
    ) -> List[Individual]:
        """Binary tournament mating selection."""
        if not population:
            return []
        if ranks is None or crowding is None:
            ranks, crowding = self.ranks_and_crowding(population)
        out: List[Individual] = []
        n = len(population)
        for _ in range(n_select):
            a, b = self.rng.randrange(n), self.rng.randrange(n)
            win = binary_tournament(
                self.rng, a, b,
                [ranks[population[i].individual_id] for i in range(n)],
                [crowding[population[i].individual_id] for i in range(n)],
            )
            out.append(population[win])
        return out

    def sort_fronts(self, population: Sequence[Individual]) -> List[List[int]]:
        rows = self._min_rows(population)
        return non_dominated_sort(rows)

    def pareto_front(self, population: Sequence[Individual]) -> List[Individual]:
        if not population:
            return []
        fronts = self.sort_fronts(population)
        return [population[i] for i in fronts[0]] if fronts else []
