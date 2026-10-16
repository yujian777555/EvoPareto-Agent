import sqlite3
from pathlib import Path

ledgers = [
    "results/pilot1_live_run/budget.sqlite",
    "results/stage1_feasibility/budget.sqlite",
    "results/stage1_6/budget.sqlite",
    "results/stage1_8/budget.sqlite",
]
print("=== SQLite ledgers ===")
g_h = g_in = g_out = g_cost = 0.0
for p in ledgers:
    f = Path(p)
    if not f.exists():
        print(p, "MISSING")
        continue
    c = sqlite3.connect(str(f))
    c.row_factory = sqlite3.Row
    r = dict(c.execute("SELECT * FROM budget WHERE id=1").fetchone())
    print(p)
    print("  HTTP=%s  in=%s  out=%s  cost=$%.6f  cap=$%s" % (
        r["physical_attempts"], r["tokens_in"], r["tokens_out"],
        r["spent_cost"], r["max_cost_usd"]))
    g_h += r["physical_attempts"]
    g_in += r["tokens_in"]
    g_out += r["tokens_out"]
    g_cost += r["spent_cost"]
    c.close()
print()
print("TOTAL: HTTP=%d  tokens_in=%d  tokens_out=%d  cost=$%.6f" % (g_h, g_in, g_out, g_cost))
