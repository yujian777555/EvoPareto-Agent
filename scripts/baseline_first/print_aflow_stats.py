import json
from pathlib import Path

d = json.loads(Path("results/stage3_0_p1_r2/trace_analysis.json").read_text(encoding="utf-8"))
for bench, variants in d.items():
    for var, a in variants.items():
        print(
            f"{a['benchmark']:28s} rounds={a['n_rounds']:2d} succ={a['n_success']:2d} "
            f"up={a['upgrades']:2d} down={a['downgrades']:2d} best={a.get('final_best_score')}"
        )
qa = json.loads(Path("results/stage3_0_p1_r2/research_questions_analysis.json").read_text(encoding="utf-8"))
print("dup_mods", qa["Q_A_success_inheritance"]["duplicate_mod_count"])
curves = qa["Q_B_diversity_collapse"]["best_score_curves"]
print("GSM8K/graphs curve", curves.get("GSM8K/graphs"))
fathers = qa["Q_B_diversity_collapse"]["father_child_counts"]
print("GSM8K/graphs fathers", fathers.get("GSM8K/graphs"))
