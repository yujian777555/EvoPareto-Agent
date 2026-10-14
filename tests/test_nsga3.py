"""NSGA-III selection tests (non-dominated sorting, reference dirs, niching)."""

import math
import random

import pytest

from src.agent.genome import AgentGenome
from src.agent.individual import Individual
from src.evolution.nsga3 import (
    NSGA3,
    dominates,
    generate_reference_directions,
    non_dominated_sort,
    niching_select,
    normalize_fitness,
    associate_to_references,
)
from src.evaluation.objectives import to_minimization


def ind_with_fitness(fit_min, gen=0):
    return Individual(
        genome=AgentGenome.random(random.Random(abs(hash(tuple(fit_min))) % 10**6)),
        fitness_vector=list(fit_min),
        generation=gen,
    )


def test_generate_reference_directions_simplex():
    dirs = generate_reference_directions(3, divisions=2)
    # C(2+3-1, 3-1) = C(4,2) = 6
    assert len(dirs) == 6
    for d in dirs:
        assert len(d) == 3
        assert abs(sum(d) - 1.0) < 1e-9
        assert all(x >= -1e-12 for x in d)


def test_generate_reference_directions_5obj():
    dirs = generate_reference_directions(5, divisions=3)
    # C(3+5-1, 5-1) = C(7,4) = 35
    assert len(dirs) == 35
    for d in dirs:
        assert abs(sum(d) - 1.0) < 1e-9


def test_dominates_minimization():
    assert dominates([1, 1], [2, 2])
    assert not dominates([2, 2], [1, 1])
    assert not dominates([1, 2], [1, 2])  # equal
    assert not dominates([1, 3], [2, 2])  # tradeoff


def test_non_dominated_sort_simple():
    # Minimization:
    # [0,0] dominates [1,1], [0,2], [2,2]
    # [1,1] and [0,2] trade off
    # both dominate [2,2]
    rows = [
        [0, 0],   # front 0
        [1, 1],   # front 1
        [0, 2],   # front 1
        [2, 2],   # front 2
    ]
    fronts = non_dominated_sort(rows)
    assert fronts[0] == [0]
    assert set(fronts[1]) == {1, 2}
    assert fronts[2] == [3]


def test_nsga3_select_keeps_size_and_best():
    # Paper semantics: high perf/eff/rob/auto good, low cost good.
    rows = [
        [1.0, 1.0, 0.0, 1.0, 1.0],  # elite
        [0.5, 0.5, 0.5, 0.5, 0.5],  # mid
        [0.2, 0.2, 0.8, 0.2, 0.2],  # bad
        [0.0, 0.0, 1.0, 0.0, 0.0],  # worst
    ]
    pop = [ind_with_fitness(r) for r in rows]
    nsga = NSGA3(n_objectives=5, divisions=2, seed=0)
    selected = nsga.select(pop, pop_size=2)
    assert len(selected) == 2
    chosen_ids = {id(s) for s in selected}
    assert id(pop[0]) in chosen_ids and id(pop[1]) in chosen_ids


def test_nsga3_select_from_larger_pool():
    rng = random.Random(0)
    pop = []
    for i in range(30):
        fit = [rng.random() for _ in range(5)]
        pop.append(ind_with_fitness(fit, gen=i))
    nsga = NSGA3(n_objectives=5, divisions=3, seed=1)
    selected = nsga.select(pop, pop_size=15)
    assert len(selected) == 15
    # All selected individuals come from the original pool ids.
    assert all(s.individual_id in {p.individual_id for p in pop} for s in selected)


def test_nsga3_select_supports_5_plus_objectives():
    rng = random.Random(2)
    for n_obj in (5, 6, 8):
        pop = [
            ind_with_fitness([rng.random() for _ in range(n_obj)]) for _ in range(25)
        ]
        nsga = NSGA3(
            n_objectives=n_obj,
            divisions=2,
            seed=3,
            maximize=tuple([True] * n_obj),
        )
        selected = nsga.select(pop, pop_size=12)
        assert len(selected) == 12


def test_normalize_and_association():
    rows = [
        [0.1, 0.2, 0.3, 0.4, 0.5],
        [0.5, 0.4, 0.3, 0.2, 0.1],
        [0.2, 0.2, 0.2, 0.2, 0.2],
    ]
    normalized, ideal, ranges = normalize_fitness(rows, [0, 1, 2])
    assert len(normalized) == 3
    assert all(r > 0 for r in ranges)
    dirs = generate_reference_directions(5, divisions=2)
    assoc, dist = associate_to_references(normalized, dirs, [0, 1, 2])
    assert set(assoc.keys()) == {0, 1, 2}
    assert all(d >= 0 for d in dist.values())


def test_niching_select_counts():
    # Construct two fronts; critical front has 4 members and we need 2.
    rows = [
        [0, 0, 0, 0, 0],
        [0, 1, 1, 1, 1],
        [1, 0, 1, 1, 1],
        [1, 1, 1, 1, 1],
    ]
    normalized, _, _ = normalize_fitness(rows, [0])
    dirs = generate_reference_directions(5, divisions=2)
    picked = niching_select(
        normalized, dirs, last_front=[1, 2, 3], n_select=2, niche_counts={i: 0 for i in range(len(dirs))}
    )
    assert len(picked) == 2
    assert len(set(picked)) == 2
    assert set(picked).issubset({1, 2, 3})


def test_nsga3_pareto_front_helper():
    rows_min = [
        [0, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
        [0, 1, 1, 1, 1],
    ]
    pop = [ind_with_fitness(r) for r in rows_min]
    nsga = NSGA3(n_objectives=5, divisions=2, seed=0)
    front = nsga.pareto_front(pop)
    assert len(front) >= 1
    assert all(f.has_fitness() for f in front)
