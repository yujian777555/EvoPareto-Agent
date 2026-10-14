import json
from pathlib import Path
d = json.loads(Path("results/benchmark_extension/summary.json").read_text(encoding="utf-8"))
for bench in ("alfworld", "webshop"):
    print("===", bench.upper(), "===")
    for r in d[bench]:
        print(
            r["Method"],
            "Succ",
            round(r["Success"]["mean"], 3),
            "+-",
            round(r["Success"]["std"], 3),
            "Cost",
            round(r["Cost"]["mean"], 6),
            "HV",
            round(r["HV"]["mean"], 3),
            "+-",
            round(r["HV"]["std"], 3),
            "IGD",
            round(r["IGD"]["mean"], 3),
            "PSS",
            round(r["PSS"]["mean"], 3),
        )
print("FIG2")
for row in d["figures"]["fig2_preference_shift"]:
    print(row)
