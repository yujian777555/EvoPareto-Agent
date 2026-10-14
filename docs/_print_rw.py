import json
from pathlib import Path
d = json.loads(Path("results/real_world/summary.json").read_text(encoding="utf-8"))
print("OVERALL")
for r in d["overall"]:
    print(r["Method"], "Succ", round(r["Success"]["mean"], 3), "+-", round(r["Success"]["std"], 3),
          "Cost", round(r["Cost"]["mean"], 6), "Lat", round(r["Latency"]["mean"], 4),
          "Tools", r["ToolCalls"]["mean"])
print("PREFERENCE")
for r in d["preference"]:
    print(r["Preference"], "Succ", round(r["Success"]["mean"], 3), "Cost", round(r["Cost"]["mean"], 6),
          "PSS", round(r["PSS"]["mean"], 3))
print("TRANSFER")
print(json.dumps(d["transfer"], indent=2))
print("TRAJ")
for c in d["trajectory"]["curve"]:
    print(c)
print("COST", json.dumps(d["cost_report"], indent=2))
