"""Phase 0 final audit checks (run from repo root)."""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agent.genome import AgentGenome, MIN_BUDGET, MAX_BUDGET
from src.agent.individual import Individual
from src.evaluation.evaluator import ToyEvaluator
from src.evaluation.objectives import to_minimization, OBJECTIVE_NAMES
from src.evolution.nsga3 import (
    NSGA3,
    dominates,
    generate_reference_directions,
    non_dominated_sort,
    pareto_front_indices,
)
from src.evolution.population import Population, PopulationConfig
from src.utils.pareto import filter_pareto_max, filter_pareto_mixed, pareto_mask_max, pareto_mask_mixed

results = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))


# ------------------------------------------------------------------ #
# 1. Agent Genome
# ------------------------------------------------------------------ #
g = AgentGenome("cot", "episodic", "self_critique", "balanced", 32)
check("genome.to_dict/from_dict", AgentGenome.from_dict(g.to_dict()) == g)
check("genome.to_json/from_json", AgentGenome.from_json(g.to_json()) == g)
check("genome.key stable", g.key() == ("cot", "episodic", "self_critique", "balanced", 32))
check("genome.replace immutable", g.replace(reasoning_budget=64).reasoning_budget == 64 and g.reasoning_budget == 32)
check("genome.comparable", g < g.replace(reasoning_budget=64) or g > g.replace(reasoning_budget=64))

bad = False
try:
    AgentGenome("bad", "none", "none", "none", 32)
except ValueError:
    bad = True
check("genome.rejects invalid strategy", bad)

bad = False
try:
    AgentGenome("cot", "none", "none", "none", 0)
except ValueError:
    bad = True
check("genome.rejects bad budget", bad)

g_min = AgentGenome("direct", "none", "none", "no_tools", MIN_BUDGET)
g_max = AgentGenome("reflexion", "hybrid", "iterative", "tool_first", MAX_BUDGET)
check("genome.budget bounds valid", g_min.reasoning_budget == MIN_BUDGET and g_max.reasoning_budget == MAX_BUDGET)

# Individual
ind = Individual(genome=g, fitness_vector=[0.5, 0.5, 0.2, 0.6, 0.7], generation=3)
check("individual.roundtrip", Individual.from_json(ind.to_json()).to_dict() == ind.to_dict())
check("individual.clone new id", ind.clone(reset_id=True).individual_id != ind.individual_id)

# ------------------------------------------------------------------ #
# 2. NSGA-III is a real implementation
# ------------------------------------------------------------------ #
src_text = pathlib.Path(ROOT / "src/evolution/nsga3.py").read_text(encoding="utf-8")
tree = ast.parse(src_text)
imports = []
for n in ast.walk(tree):
    if isinstance(n, ast.Import):
        imports += [a.name for a in n.names]
    elif isinstance(n, ast.ImportFrom):
        imports.append(n.module or "")
blackbox = [i for i in imports if any(k in i for k in ("pymoo", "deap", "platypus", "pymoo", "nsga"))]
check("nsga3.no blackbox library", not blackbox, f"imports={imports}")

funcs = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
need = {
    "generate_reference_directions",
    "non_dominated_sort",
    "dominates",
    "normalize_fitness",
    "associate_to_references",
    "niching_select",
}
check("nsga3.has core algorithm pieces", need <= funcs, f"found={sorted(need & funcs)}")

# Reference directions: Das-Dennis count C(H+M-1, M-1)
for m, h, expect in [(3, 2, 6), (5, 3, 35), (5, 2, 15)]:
    dirs = generate_reference_directions(m, h)
    ok = len(dirs) == expect and all(abs(sum(d) - 1.0) < 1e-9 for d in dirs)
    check(f"nsga3.reference_directions M={m} H={h}", ok, f"n={len(dirs)} expect={expect}")

# Non-dominated sorting correctness
rows = [[0, 0], [1, 1], [0, 2], [2, 2]]
fronts = non_dominated_sort(rows)
check("nsga3.non_dominated_sort ranks", fronts[0] == [0] and set(fronts[1]) == {1, 2} and fronts[2] == [3])

# Dominance
check("nsga3.dominates min semantics", dominates([1, 1], [2, 2]) and not dominates([1, 3], [2, 2]))

# Selection keeps best under clear dominance (paper semantics)
pop = []
elite_fit = [1.0, 1.0, 0.0, 1.0, 1.0]
mid_fit = [0.5, 0.5, 0.5, 0.5, 0.5]
bad_fit = [0.0, 0.0, 1.0, 0.0, 0.0]
worse_fit = [0.0, 0.0, 1.0, 0.0, 0.0]
for i, fit in enumerate([elite_fit, mid_fit, bad_fit, worse_fit]):
    pop.append(Individual(genome=g.replace(reasoning_budget=MIN_BUDGET + 8 * i), fitness_vector=fit, generation=0))
sel = NSGA3(n_objectives=5, divisions=2, seed=0).select(pop, 2)
check("nsga3.select keeps elite", any(s.fitness_vector == elite_fit for s in sel) and any(s.fitness_vector == mid_fit for s in sel), f"got={[s.fitness_vector for s in sel]}")

# Many-objective support >= 5
for n_obj in (5, 6, 8):
    rng = random.Random(n_obj)
    pool = [
        Individual(genome=g, fitness_vector=[rng.random() for _ in range(n_obj)], generation=0)
        for _ in range(25)
    ]
    out = NSGA3(n_objectives=n_obj, divisions=2, seed=0, maximize=tuple([True] * n_obj)).select(pool, 12)
    check(f"nsga3.select supports {n_obj} objectives", len(out) == 12)

# ------------------------------------------------------------------ #
# 3. Pareto selection
# ------------------------------------------------------------------ #
check("objectives.names", list(OBJECTIVE_NAMES) == ["performance", "efficiency", "cost", "robustness", "autonomy"])
mini = to_minimization([0.7, 0.6, 0.2, 0.8, 0.9])
check("objectives.min conversion signs", mini == [-0.7, -0.6, 0.2, -0.8, -0.9])

# Population front equals brute-force mixed filter on raw fitness
ev = ToyEvaluator(noise_scale=0.0)
cfg = PopulationConfig(pop_size=20, n_offspring=20, seed=7)
pop = Population(evaluator=ev.evaluate, config=cfg)
pop.initialize()
pop.run(3)
all_rows = [list(ind.fitness_vector) for ind in pop.individuals]
manual = filter_pareto_mixed(all_rows)
algo_rows = [list(ind.fitness_vector) for ind in pop.pareto_front()]
check("pareto.front size matches brute force", len(algo_rows) == len(manual), f"algo={len(algo_rows)} manual={len(manual)}")

mask = pareto_mask_mixed(all_rows)
ok = all(any(mask[i] and all_rows[i] == row for i in range(len(all_rows))) for row in algo_rows)
check("pareto.front members are non-dominated", ok)

# Internal minimization front agrees with mixed-direction maximization front
from src.evolution.nsga3 import pareto_front_indices as nds_idx
from src.utils.pareto import pareto_mask_mixed, filter_pareto_mixed

min_rows = [to_minimization(r) for r in all_rows]
idx_min = set(nds_idx(min_rows))
mixed_mask = pareto_mask_mixed(all_rows)
check(
    "pareto.min/mixed front indices agree",
    idx_min == {i for i, m in enumerate(mixed_mask) if m},
    f"min={len(idx_min)} mixed={sum(mixed_mask)}",
)

# Regression: constructed vectors where signs matter
from src.evolution.nsga3 import dominates as dom_min
from src.utils.pareto import dominates_mixed

A = [0.9, 0.5, 0.2, 0.5, 0.5]
B = [0.5, 0.5, 0.5, 0.5, 0.5]
check("pareto.mixed dominance uses cost direction", dominates_mixed(A, B) and not dominates_mixed(B, A))
check("pareto.not all-max on raw", not __import__("src.utils.pareto", fromlist=["dominates_max"]).dominates_max(A, B))

# Toy evaluator tradeoff: neither cheap nor strong dominates the other
cheap = AgentGenome("direct", "none", "none", "no_tools", 8)
strong = AgentGenome("tree_search", "hybrid", "iterative", "tool_first", 128)
c, s = ev.evaluate(cheap), ev.evaluate(strong)
check("evaluator.tradeoff exists", not dominates(to_minimization(c), to_minimization(s)) and not dominates(to_minimization(s), to_minimization(c)))
check("evaluator.deterministic", ToyEvaluator(noise_scale=1.0).evaluate(g) == ToyEvaluator(noise_scale=1.0).evaluate(g))
check("evaluator.5 objectives in [0,1]", all(0.0 <= v <= 1.0 for v in ToyEvaluator().evaluate(g)))

# ------------------------------------------------------------------ #
# 4. Tests (structural)
# ------------------------------------------------------------------ #
test_files = sorted((ROOT / "tests").glob("test_*.py"))
names = [p.name for p in test_files]
required = {
    "test_genome_serialization.py": ["test_to_dict_from_dict_roundtrip", "test_to_json_from_json_roundtrip"],
    "test_mutation.py": ["test_prompt_mutation_changes_planner", "test_memory_mutation_changes_memory", "test_budget_mutation_within_bounds_and_snapped", "test_tool_mutation_changes_tool_policy"],
    "test_population.py": ["test_population_initialize_and_size", "test_next_generation_maintains_size_and_progress"],
    "test_nsga3.py": ["test_non_dominated_sort_simple", "test_nsga3_select_keeps_size_and_best", "test_generate_reference_directions_5obj", "test_niching_select_counts"],
    "test_pareto_front.py": ["test_population_front_matches_manual_pareto", "test_pareto_mask_simple"],
}
ok = True
missing = []
for fname, cases in required.items():
    path = ROOT / "tests" / fname
    if not path.exists():
        ok = False
        missing.append(fname)
        continue
    text = path.read_text(encoding="utf-8")
    for case in cases:
        if f"def {case}" not in text:
            ok = False
            missing.append(f"{fname}:{case}")
check("tests.required cases present", ok, f"missing={missing}" if missing else f"files={names}")

# ------------------------------------------------------------------ #
# 5. Demo reproducibility
# ------------------------------------------------------------------ #
sys.path.insert(0, str(ROOT / "experiments"))
from run_nsga3_demo import run_experiment

s1 = run_experiment(pop_size=30, n_generations=8, seed=123)
p1 = json.loads((ROOT / "results" / "pareto_front.json").read_text(encoding="utf-8"))
h1 = json.loads((ROOT / "results" / "population_history.json").read_text(encoding="utf-8"))
hash1 = hashlib.sha256(json.dumps(p1, sort_keys=True).encode()).hexdigest()

s2 = run_experiment(pop_size=30, n_generations=8, seed=123)
p2 = json.loads((ROOT / "results" / "pareto_front.json").read_text(encoding="utf-8"))
hash2 = hashlib.sha256(json.dumps(p2, sort_keys=True).encode()).hexdigest()

check("demo.same seed reproducible", hash1 == hash2, f"hash={hash1[:12]}")
check("demo.pareto file written", p1["n_points"] > 0 and "points" in p1)
check("demo.history file written", h1["n_genereds" if False else "n_generations"] == 8 and len(h1["histories"]) == 1)
check("demo.summary written", s1["pareto_size"] > 0)

# Restore default demo outputs so results/ matches README quick-start numbers
final = run_experiment()  # pop_size=60, gens=25, seed=42
check("demo.default run ok", final["pareto_size"] > 0 and final["n_generations"] == 25)

# ------------------------------------------------------------------ #
print("\n=== AUDIT SUMMARY ===")
failed = [r for r in results if not r[1]]
print(f"total={len(results)} passed={len(results)-len(failed)} failed={len(failed)}")
for name, ok, detail in failed:
    print("FAIL:", name, detail)
sys.exit(1 if failed else 0)
